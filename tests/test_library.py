"""Isolated library tests: never touch the user's saved records."""
import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import library
from app.main import app


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tracks = self.root / 'library' / 'tracks'
        self.tracks.mkdir(parents=True)
        self.index = self.tracks.parent / 'tracks.json'
        self.index.write_text('[]')
        self.patchers = [patch.object(library, key, value) for key, value in (
            ('LIBRARY_DIR', self.tracks.parent), ('TRACKS_DIR', self.tracks), ('INDEX_PATH', self.index))]
        for p in self.patchers:
            p.start()
        self.addCleanup(self.temp.cleanup)
        for p in self.patchers:
            self.addCleanup(p.stop)
        self.source = self.root / 'session.mp3'
        self.source.write_bytes(b'original audio')
        self.client = TestClient(app)

    def add_song(self, **extra):
        return library.add({'title': 'Test record', **extra}, self.source, None, session_id='original')

    def test_delete_persists_only_selected_copy_and_keeps_session(self):
        first = self.add_song()
        second = self.add_song()
        result = self.client.delete('/api/library/' + first['id'])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {'removed': first['id']})
        self.assertEqual([t['id'] for t in library.list_tracks()], [second['id']])
        self.assertEqual(json.loads(self.index.read_text()), [second])
        self.assertFalse((self.tracks / first['id']).exists())
        self.assertTrue((self.tracks / second['id'] / 'audio.mp3').exists())
        self.assertEqual(self.source.read_bytes(), b'original audio')

    def test_rejects_non_generated_ids_before_filesystem_access(self):
        for bad in ('..', '../session.mp3', '/tmp/abcdef12', 'ABCDEF12', 'abcdef1', 'abcdef123', 'abcdef12\n', 'zzzzzzzz'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    library.remove(bad)
        self.assertEqual(self.client.delete('/api/library/not-an-id').status_code, 400)

    def test_unknown_id_is_not_success(self):
        self.assertEqual(self.client.delete('/api/library/abcdef12').status_code, 404)
        self.assertEqual(self.index.read_text(), '[]')

    def test_index_replace_failure_keeps_audio_and_index(self):
        song = self.add_song()
        with patch.object(Path, 'replace', side_effect=PermissionError('read-only index')):
            with self.assertRaises(OSError):
                library.remove(song['id'])
        self.assertEqual(library.list_tracks(), [song])
        self.assertEqual((self.tracks / song['id'] / 'audio.mp3').read_bytes(), self.source.read_bytes())

    def test_cleanup_failure_is_reported_and_keeps_entry(self):
        song = self.add_song()
        with self.assertLogs('aijukebox.library', level='ERROR'), patch.object(library.shutil, 'rmtree', side_effect=PermissionError('locked file')):
            response = self.client.delete('/api/library/' + song['id'])
        self.assertEqual(response.status_code, 500)
        self.assertIn('remove', response.json()['detail'].lower())
        self.assertEqual(library.list_tracks(), [song])
        self.assertTrue((self.tracks / song['id'] / 'audio.mp3').exists())

    def test_partial_cleanup_failure_restores_entry_and_remaining_files(self):
        song = self.add_song()
        tdir = self.tracks / song['id']
        original_cover = self.root / 'original-session-cover.png'
        original_cover.write_bytes(b'original cover')
        (tdir / 'cover.png').write_bytes(original_cover.read_bytes())

        def partial_cleanup(staged):
            (staged / 'cover.png').unlink()
            raise PermissionError('audio is locked after cover was removed')

        with self.assertLogs('aijukebox.library', level='ERROR'), patch.object(library.shutil, 'rmtree', side_effect=partial_cleanup):
            response = self.client.delete('/api/library/' + song['id'])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(library.list_tracks(), [song])
        self.assertEqual((tdir / 'audio.mp3').read_bytes(), b'original audio')
        self.assertFalse((tdir / 'cover.png').exists())
        self.assertEqual(self.source.read_bytes(), b'original audio')
        self.assertEqual(original_cover.read_bytes(), b'original cover')
        self.assertEqual(list(self.tracks.parent.glob('.removing-*')), [])

    def test_symlinked_tracks_root_cannot_delete_outside_library(self):
        song = self.add_song()
        outside = self.root / 'outside'
        self.tracks.rename(outside)
        self.tracks.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            library.remove(song['id'])
        self.assertTrue((outside / song['id'] / 'audio.mp3').exists())

    def test_corrupt_index_is_not_silently_replaced_on_add_or_remove(self):
        song = self.add_song()
        for broken in ('not JSON', '{}', '[{"title": "missing ID"}]'):
            self.index.write_text(broken)
            with self.subTest(broken=broken):
                with self.assertRaises(OSError):
                    library.remove(song['id'])
                with self.assertRaises(OSError):
                    self.add_song()
                self.assertEqual(self.index.read_text(), broken)
                self.assertTrue((self.tracks / song['id'] / 'audio.mp3').exists())

    def test_add_preserves_cover_metadata_with_older_caller_defaults(self):
        direction = {'palette': 'red and ivory', 'medium': 'Paper cutout', 'composition': 'off-center', 'approach': 'symbolic object'}
        rich = self.add_song(art_direction=direction, cover_prompt='A red moon')
        self.assertEqual(rich['art_direction'], direction)
        self.assertEqual(rich['cover_prompt'], 'A red moon')
        old = self.add_song()
        self.assertEqual(old['art_direction'], {})
        self.assertEqual(old['cover_prompt'], '')

    def test_concurrent_adds_and_removals_do_not_lose_index_updates(self):
        originals = [self.add_song() for _ in range(6)]
        barrier = threading.Barrier(12)

        def change(i):
            barrier.wait(timeout=5)
            if i < 6:
                library.remove(originals[i]['id'])
                return None
            return self.add_song()

        with ThreadPoolExecutor(max_workers=12) as pool:
            added = [t for t in pool.map(change, range(12)) if t]
        expected = {t['id'] for t in added}
        self.assertEqual({t['id'] for t in library.list_tracks()}, expected)
        self.assertEqual({p.name for p in self.tracks.iterdir()}, expected)
        self.assertEqual({t['id'] for t in json.loads(self.index.read_text())}, expected)

    def test_symlinked_track_and_nested_symlink_never_delete_target(self):
        song = self.add_song()
        tdir = self.tracks / song['id']
        outside = self.root / 'outside'
        tdir.rename(outside)
        tdir.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            library.remove(song['id'])
        self.assertTrue((outside / 'audio.mp3').exists())
        tdir.unlink()
        tdir.mkdir()
        (tdir / 'original').symlink_to(self.source)
        library.remove(song['id'])
        self.assertEqual(self.source.read_bytes(), b'original audio')

    def test_missing_directory_is_an_error_not_silent_success(self):
        song = self.add_song()
        import shutil
        shutil.rmtree(self.tracks / song['id'])
        with self.assertLogs('aijukebox.library', level='ERROR'):
            response = self.client.delete('/api/library/' + song['id'])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(library.list_tracks(), [song])
