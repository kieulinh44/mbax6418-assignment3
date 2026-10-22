"""Naming regression checks: no network calls or real collection writes."""
import random
import unittest
from concurrent.futures import ThreadPoolExecutor
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

from app import jukebox, naming, songs


class NamingTests(unittest.TestCase):
    def test_exhausted_naming_drafts_never_reach_audio_or_art_generation(self):
        saved = [{'title': 'Echo Tides', 'artist': 'Glass Horizon'}]
        director = naming.NamingDirector(history=lambda: saved)
        sid = 'naming-test'
        with tempfile.TemporaryDirectory() as temp, patch.object(jukebox, 'SESSIONS_DIR', Path(temp)), patch.dict(jukebox._sessions, {sid: {'progress': {}}}, clear=True), patch.object(naming, 'director', director), patch.object(songs, 'chat_json', return_value=dict(saved[0])) as chat, patch.object(jukebox, '_generate_song') as audio, patch.object(jukebox.art_mod, 'cover_for') as cover, patch.object(jukebox.library_mod, 'add') as add:
            (Path(temp) / sid).mkdir()
            with self.assertLogs('aijukebox.jukebox', level='ERROR'):
                jukebox._build(sid, {'genre': 'jazz', 'custom_single': True}, 1)
            session = jukebox.get(sid)
            assert session is not None
            self.assertEqual(session['state'], 'error')
            self.assertIn('three drafts', session['error'])
            self.assertEqual(chat.call_count, 3)
            audio.assert_not_called()
            cover.assert_not_called()
            add.assert_not_called()

    def test_artist_signature_words_are_not_reused_with_a_different_prefix(self):
        saved = [{'title': 'Grab the Handle', 'artist': 'The Porcelain Commuters'},
                 {'title': 'Ticket Stub', 'artist': 'K. Voss'}]
        director = naming.NamingDirector(history=lambda: saved)
        for artist in ('The Glass Commuters', 'Elara Voss'):
            with self.subTest(artist=artist):
                reasons = director.reserve({'title': 'Keep the Receipt', 'artist': artist})
                self.assertTrue(any('artist' in reason.lower() for reason in reasons))
        self.assertIn('voss', director.brief()['artist_words_to_avoid'])

    def test_artist_cannot_be_a_reworded_copy_of_the_song_title(self):
        director = naming.NamingDirector(history=lambda: [])
        reasons = director.reserve({'title': 'Paper Lanterns', 'artist': 'The Paper Lantern'})
        self.assertTrue(any('artist' in reason.lower() for reason in reasons))

    def test_composer_retries_the_whole_spec_with_history_and_feedback(self):
        saved = [{'title': 'Echo Tides', 'artist': 'Glass Horizon'}]
        director = naming.NamingDirector(history=lambda: saved, rng=random.Random(3))
        duplicate = {'title': 'Echo Tides', 'artist': 'Glass Horizon', 'lyrics': '[Chorus] Echo tides', 'cover_prompt': 'An ocean'}
        fresh = {'title': 'Keep the Receipt', 'artist': 'Maren Quill', 'lyrics': '[Chorus] Keep the receipt', 'cover_prompt': 'A folded receipt'}
        with patch.object(naming, 'director', director), patch.object(songs, 'chat_json', side_effect=[duplicate, fresh]) as chat:
            track = songs.compose_track({'genre': 'synthwave', 'theme': 'regret', 'vocals': True})
        self.assertEqual(track['title'], 'Keep the Receipt')
        self.assertEqual(track['artist'], 'Maren Quill')
        self.assertEqual(track['lyrics'].split(), fresh['lyrics'].split())
        self.assertEqual(track['cover_prompt'], fresh['cover_prompt'])
        self.assertEqual(chat.call_count, 2)
        self.assertIn('Echo Tides', chat.call_args_list[0].args[1])
        self.assertIn('Glass Horizon', chat.call_args_list[0].args[1])
        self.assertIn('RETRY', chat.call_args_list[1].args[1])
        self.assertIn('too close', chat.call_args_list[1].args[1])

    def test_repeated_bad_drafts_fail_after_three_attempts_without_renaming(self):
        saved = [{'title': 'Echo Tides', 'artist': 'Glass Horizon'}]
        director = naming.NamingDirector(history=lambda: saved)
        with patch.object(naming, 'director', director), patch.object(songs, 'chat_json', return_value=dict(saved[0])) as chat:
            with self.assertRaisesRegex(RuntimeError, 'three drafts'):
                songs.compose_track({'genre': 'jazz', 'vocals': False})
        self.assertEqual(chat.call_count, 3)
        self.assertEqual(director.brief()['recent_titles'], ['Echo Tides'])

    def test_pending_reservations_are_atomic_for_simultaneous_requests(self):
        director = naming.NamingDirector(history=lambda: [])
        barrier = threading.Barrier(2)

        def reserve(_):
            barrier.wait(timeout=5)
            return director.reserve({'title': 'Keep the Receipt', 'artist': 'Maren Quill'})

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(sum(not reasons for reasons in results), 1)

    def test_saved_history_is_reloaded_and_not_double_counted_with_reservations(self):
        saved = []
        director = naming.NamingDirector(history=lambda: saved)
        track = {'title': 'Paper Lanterns', 'artist': 'Maren Quill'}
        self.assertEqual(director.reserve(track), [])
        saved.append(track)
        self.assertEqual(director.reserve({'title': 'Paper Moon', 'artist': 'Dovren'}), [])
        reasons = director.reserve({'title': 'Paper Weather', 'artist': 'Celand Rook'})
        self.assertTrue(any('paper' in reason.lower() for reason in reasons))
        restarted = naming.NamingDirector(history=lambda: saved)
        self.assertTrue(restarted.reserve(track))
        self.assertIn('Paper Lanterns', restarted.brief()['recent_titles'])

    def test_naming_briefs_rotate_forms_and_include_saved_and_pending_names(self):
        saved = [{'title': 'Echo Tides', 'artist': 'Glass Horizon'}]
        director = naming.NamingDirector(history=lambda: saved, rng=random.Random(42))
        self.assertEqual(director.reserve({'title': 'Keep the Receipt', 'artist': 'Maren Quill'}), [])
        briefs = [director.brief() for _ in range(8)]
        self.assertEqual(len({b['title_form'] for b in briefs}), 8)
        self.assertEqual(len({b['artist_form'] for b in briefs}), 8)
        self.assertIn('Echo Tides', briefs[0]['recent_titles'])
        self.assertIn('Keep the Receipt', briefs[0]['recent_titles'])
        self.assertIn('Glass Horizon', briefs[0]['recent_artists'])
        self.assertEqual(saved, [{'title': 'Echo Tides', 'artist': 'Glass Horizon'}])

    def test_recurrent_words_are_discouraged_across_title_and_artist_fields(self):
        saved = [{'title': 'Neon Pulse', 'artist': 'Velvet Circuit'},
                 {'title': 'Neon Veins', 'artist': 'Velvet Orchard'}]
        director = naming.NamingDirector(history=lambda: saved)
        reasons = director.reserve({'title': 'Neon Weather', 'artist': 'Maren Quill'})
        self.assertTrue(any('neon' in reason.lower() for reason in reasons))
        reasons = director.reserve({'title': 'Keep the Receipt', 'artist': 'Velvet Workshop'})
        self.assertTrue(any('velvet' in reason.lower() for reason in reasons))
        # A listener's explicit subject is not a blanket ban on that concept.
        self.assertEqual(director.reserve({'title': 'Neon Weather', 'artist': 'Maren Quill'}, theme='neon reflections'), [])

    def test_existing_collection_blocks_case_punctuation_and_suffix_variants(self):
        saved = [{'title': 'Echo Tides', 'artist': 'Glass Horizon', 'set_genre': 'metal'}]
        director = naming.NamingDirector(history=lambda: saved, rng=random.Random(42))
        for title in ('echo tides!', 'Echo Tide', 'The Echo Tides', 'Echo Tides 2'):
            with self.subTest(title=title):
                reasons = director.reserve({'title': title, 'artist': 'Maren Quill'})
                self.assertTrue(reasons)
                self.assertTrue(any('title' in reason.lower() for reason in reasons))
        reasons = director.reserve({'title': 'Keep the Receipt', 'artist': 'Glass-Horizon'})
        self.assertTrue(any('artist' in reason.lower() for reason in reasons))


if __name__ == '__main__':
    unittest.main()
