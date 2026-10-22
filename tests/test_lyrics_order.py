"""Lyrics preserve the intended performance order and service revisions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import clients, jukebox, library, songs


class LyricsOrderTests(unittest.TestCase):
    def test_saved_library_retains_service_sheet_and_original_written_lyrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tracks = root / 'tracks'
            tracks.mkdir()
            index = root / 'tracks.json'
            index.write_text('[]')
            audio = root / 'original.mp3'
            audio.write_bytes(b'fixture')
            with patch.object(library, 'TRACKS_DIR', tracks), patch.object(library, 'INDEX_PATH', index):
                entry = library.add({'title': 'Carry Me Home', 'lyrics': 'Service lyric sheet',
                                     'written_lyrics': 'Original written sheet', 'lyrics_source': 'music_service'},
                                    audio, None, session_id='test')
                restored = library.list_tracks()[0]
            self.assertEqual(restored['lyrics'], entry['lyrics'])
            self.assertEqual(restored['written_lyrics'], 'Original written sheet')
            self.assertEqual(restored['lyrics_source'], 'music_service')

    def test_hook_first_excerpt_preserves_later_sections_in_sequence(self):
        original = ('[Intro]\n[Instrumental]\n[Verse 1]\nBefore the storm\n'
                    '[Chorus]\nCarry me home\n[Verse 2]\nWindows glow tonight\n'
                    '[Final Chorus]\nCarry me home again\n[Outro]\n[Instrumental]')
        _, result = songs.short_vocal_arrangement('Bright pop vocals', original, 60)
        self.assertEqual(result, '[Chorus]\nCarry me home\n\n[Verse 2]\nWindows glow tonight\n\n[Final Chorus]\nCarry me home again')

    def test_song_manifest_uses_service_lyrics_instead_of_discarding_revisions(self):
        spec = songs.normalize({'title': 'Carry Me Home', 'artist': 'Orin Vale',
                                'lyrics': '[Chorus]\nCarry me home\n[Verse 2]\nWindows glow'},
                               {'vocals': True, 'duration_sec': 60})
        performed = '[Verse]\nWindows glow\n[Chorus]\nCarry me home\nCarry me home'
        sid = 'lyric-order-test'
        with tempfile.TemporaryDirectory() as temp, patch.object(jukebox, 'SESSIONS_DIR', Path(temp)), patch.dict(jukebox._sessions, {sid: {'progress': {}}}, clear=True), patch.object(songs, 'compose_track', return_value=spec), patch.object(jukebox, '_generate_song', return_value=(b'audio', {'lyrics': performed})), patch.object(jukebox.art_mod, 'cover_for', return_value=b''), patch.object(library, 'add') as add:
            (Path(temp) / sid).mkdir()
            jukebox._build(sid, {'custom_single': True, 'vocals': True}, 1)
            state = jukebox.get(sid)
            assert state is not None
            self.assertEqual(state['state'], 'ready')
            track = state['manifest']['tracks'][0]
            self.assertEqual(track['lyrics'], performed)
            self.assertEqual(track['written_lyrics'], spec['lyrics'])
            self.assertEqual(track['lyrics_source'], 'music_service')
            self.assertEqual(add.call_args.args[0]['lyrics'], performed)


if __name__ == '__main__':
    unittest.main()
