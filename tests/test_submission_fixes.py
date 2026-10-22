"""Regression checks for submission fixes; class services are mocked."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app import djs, jukebox, clients
from app.main import app


class SubmissionFixTests(unittest.TestCase):
    def test_dj_uses_nested_metadata_and_rejects_missing_introductions(self):
        track = {'title': 'Morning', 'artist': 'A', 'meta': {'bpm': 111, 'genres': 'jazz'}}
        script = {'intro': 'Welcome', 'tracks': ['Here is Morning'], 'outro': 'Goodbye'}
        with patch.object(djs, 'chat_json', return_value=script) as chat:
            self.assertEqual(djs.script_for('neon_nina', [track]), script)
            self.assertIn('111 BPM', chat.call_args.args[1])
            self.assertIn('jazz', chat.call_args.args[1])
        with patch.object(djs, 'chat_json', return_value={**script, 'tracks': []}):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                djs.script_for('neon_nina', [track])

    def test_reference_is_sent_only_in_server_speech_request(self):
        response = Mock(content=b'speech')
        with patch.object(clients.SESSION, 'post', return_value=response) as post:
            self.assertEqual(clients.generate_speech('Hello', reference_audio=b'reference'), b'speech')
            self.assertEqual(post.call_args.kwargs['json']['ref_audio'], base64.b64encode(b'reference').decode())
            self.assertEqual(post.call_args.kwargs['json']['voice'], 'default')
        with patch.object(clients.SESSION, 'post', return_value=response) as post:
            clients.generate_speech('Hello')
            self.assertNotIn('ref_audio', post.call_args.kwargs['json'])

    def test_upload_validates_and_never_puts_reference_in_options(self):
        client = TestClient(app)
        with patch.object(jukebox, 'start', return_value='example') as start:
            response = client.post('/api/jam-with-voice', data={'options': '{}'}, files={'reference': ('voice.wav', b'RIFF1234WAVEdata', 'audio/wav')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(start.call_args.kwargs['reference_audio'], b'RIFF1234WAVEdata')
            self.assertNotIn('reference_audio', start.call_args.args[0])
            response = client.post('/api/jam-with-voice', data={'options': '{}'}, files={'reference': ('voice.wav', b'not audio')})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(start.call_count, 1)

    def test_vocals_forward_lyrics_and_language_and_reject_tag_only_lyrics(self):
        spec = {'caption': 'Pop', 'lyrics': '[Chorus]\nMorning light carry me home', 'vocal_language': 'en'}
        with patch.object(clients, 'generate_song', return_value=(b'music', {})) as generate:
            jukebox._generate_song(spec, {'vocals': True, 'duration_sec': 60})
            self.assertIn('Morning light', generate.call_args.args[1])
            self.assertEqual(generate.call_args.kwargs['vocal_language'], 'en')
        with patch.object(clients, 'generate_song') as generate:
            with self.assertRaisesRegex(ValueError, 'no singable lyrics'):
                jukebox._generate_song({'caption': 'Pop', 'lyrics': '[Verse]\n[Chorus]'}, {'vocals': True, 'duration_sec': 120})
            generate.assert_not_called()

    def test_music_payload_preserves_vocal_direction(self):
        with patch.object(clients, '_post_json', side_effect=RuntimeError('captured')) as post:
            with self.assertRaisesRegex(RuntimeError, 'captured'):
                clients.generate_song('Lead singer', '[Chorus]\nHello morning', vocal_language='en')
        payload = post.call_args.args[1]
        self.assertEqual(payload['lyrics'], '[Chorus]\nHello morning')
        self.assertEqual(payload['vocal_language'], 'en')
        self.assertFalse(payload['use_cot_caption'])
        self.assertFalse(payload['use_cot_language'])
        self.assertFalse(payload['use_format'])

    def build(self, cover):
        spec = {'title': 'Morning', 'artist': 'A', 'caption': 'Jazz morning', 'bpm': 110, 'genres': 'jazz', 'key_scale': 'C major', 'lyrics': ''}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        sid = 'regression'
        (Path(directory.name) / sid).mkdir()
        jukebox._sessions[sid] = {'id': sid, 'progress': {}}
        self.addCleanup(jukebox._sessions.pop, sid, None)
        with patch.object(jukebox, 'SESSIONS_DIR', Path(directory.name)), patch.object(jukebox.songs_mod, 'compose_track', return_value=spec), patch.object(jukebox, '_generate_song', return_value=(b'music', {})), patch.object(jukebox.art_mod, 'cover_for', return_value=cover), patch.object(jukebox.library_mod, 'add') as add, patch.object(jukebox.djs_mod, 'script_for', return_value={}), patch.object(jukebox.djs_mod, 'render_script', return_value={'intro': b'intro', 'tracks': [b'introduction'], 'outro': b'outro'}):
            jukebox._build(sid, {}, 1)
            return jukebox.get(sid), add.call_count

    def test_track_introduction_precedes_its_song(self):
        session, added = self.build(b'cover')
        self.assertEqual(session['state'], 'ready')
        self.assertEqual([t['kind'] for t in session['manifest']['playlist']], ['intro', 'chat', 'song', 'outro'])
        self.assertEqual(added, 1)

    def test_empty_cover_is_nonfatal_and_song_still_builds(self):
        # Reconciled with teammates' lyric-order suite (2026-10-22): a failed
        # FLUX cover must not kill the whole set — the song stays playable.
        session, added = self.build(b'')
        self.assertEqual(session['state'], 'ready')
        self.assertEqual([t['kind'] for t in session['manifest']['playlist']], ['intro', 'chat', 'song', 'outro'])
        self.assertEqual(session['manifest']['tracks'][0]['art'], '')
        self.assertEqual(added, 1)
