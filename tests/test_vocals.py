"""Duration-aware vocal arrangements; no AI services used."""
import unittest
from unittest.mock import patch

from app import jukebox, songs
from app.main import JamOptions
from pydantic import ValidationError


class VocalArrangementTests(unittest.TestCase):
    def test_prechorus_does_not_displace_the_actual_title_hook(self):
        lyrics = '[Pre-Chorus]\nWait for the morning\nWait for the morning\nWait for the morning\n[Chorus]\nCarry me home\nThrough the rain'
        _, adapted = songs.short_vocal_arrangement('Bright pop', lyrics, 10)
        self.assertTrue(adapted.startswith('[Chorus]\nCarry me home'))

    def test_vocal_duration_floor_is_validated_for_api_requests(self):
        for duration in (10, 30, 59):
            with self.subTest(duration=duration), self.assertRaises(ValidationError):
                JamOptions(vocals=True, duration_sec=duration)
        self.assertEqual(JamOptions().duration_sec, 60)
        self.assertEqual(JamOptions(vocals=True, duration_sec=60).duration_sec, 60)
        self.assertEqual(JamOptions(vocals=False, duration_sec=10).duration_sec, 10)

    def test_audio_boundary_refuses_unsupported_short_vocals_before_generation(self):
        with patch('app.clients.generate_song') as generate:
            with self.assertRaisesRegex(ValueError, 'at least 60 seconds'):
                jukebox._generate_song({'caption': 'Pop vocals', 'lyrics': 'Stay with me'},
                                       {'vocals': True, 'duration_sec': 10})
        generate.assert_not_called()

    def test_instrumental_requests_still_submit_no_lyrics(self):
        spec = {'caption': 'Soft piano', 'lyrics': '[Chorus]\nUnexpected singing'}
        with patch('app.clients.generate_song', return_value=(b'audio', {})) as generate:
            jukebox._generate_song(spec, {'duration_sec': 10, 'vocals': False})
        self.assertEqual(generate.call_args.args[1], '')
        self.assertEqual(generate.call_args.args[0], 'Soft piano')

    def test_longer_vocals_keep_full_structure(self):
        lyrics = '[Intro]\n[Verse 1]\nThe porch is bright\n[Chorus]\nCarry me home'
        self.assertEqual(songs.short_vocal_arrangement('Warm country vocals', lyrics, 90),
                         ('Warm country vocals', lyrics))

    def test_short_arrangement_is_idempotent(self):
        first = songs.short_vocal_arrangement('Bright pop', '[Chorus]\nCarry me home\nThrough the rain', 10)
        self.assertEqual(songs.short_vocal_arrangement(*first, 10), first)

    def test_short_vocal_uses_hook_first_with_a_duration_budget(self):
        prompt = songs._user_prompt({'vocals': True, 'duration_sec': 10}, 0, 1)
        self.assertIn('Start singing immediately', prompt)
        self.assertIn('at most 12 sung words', prompt)
        self.assertIn('No instrumental intro', prompt)

    def test_short_vocal_normalization_preserves_hook_and_removes_intro(self):
        spec = {'title': 'Carry Me Home', 'instrumental': True,
                'caption': 'A slow build from a long instrumental opening.',
                'lyrics': '[Intro]\n[Instrumental]\n\n[Verse 1]\n' + 'Rain falls down ' * 25 +
                          '\n[Chorus]\nCarry me home\nThrough the rain\nCarry me home\nAgain and again\n[Outro]\n[Instrumental]'}
        track = songs.normalize(spec, {'vocals': True, 'duration_sec': 10})
        self.assertFalse(track['instrumental'])
        self.assertTrue(track['lyrics'].startswith('[Chorus]'))
        self.assertIn('Carry me home', track['lyrics'])
        self.assertLessEqual(len(' '.join(line for line in track['lyrics'].splitlines()
                                        if not line.startswith('[')).split()), 12)
        self.assertNotIn('[Intro]', track['lyrics'])
        self.assertIn('Start singing immediately', track['caption'])

    def test_rendering_short_vocal_also_guards_older_specs(self):
        spec = {'caption': 'Sparse opening, big chorus later',
                'lyrics': '[Intro]\n[Instrumental]\n[Chorus]\nCarry me home\nThrough the rain',
                'bpm': 100}
        with patch('app.clients.generate_song', return_value=(b'audio', {})) as generate:
            jukebox._generate_song(spec, {'duration_sec': 60, 'vocals': True})
        self.assertEqual(generate.call_args.kwargs['duration'], 60)
        self.assertIn('Start singing immediately', generate.call_args.args[0])
        self.assertTrue(generate.call_args.args[1].startswith('[Chorus]'))


if __name__ == '__main__':
    unittest.main()
