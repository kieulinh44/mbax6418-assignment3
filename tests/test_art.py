"""Fast, deterministic checks of cover direction, without calling AI services."""
import random
import unittest
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import art, jukebox, songs


class ArtDirectionTests(unittest.TestCase):
    def test_rendering_a_legacy_brief_adds_richness_without_losing_palette_or_medium(self):
        track = {'title': 'Paper Lanterns', 'genres': 'synthwave', 'art_direction': {
            'palette': 'gold and indigo', 'medium': 'oil painting',
            'composition': 'one object on an empty background', 'approach': 'a lantern'}}
        with patch.object(art, 'generate_cover_art', return_value=b'image') as render:
            art.cover_for(track)
            direction = track['art_direction']
            self.assertTrue(direction.get('richness'))
            self.assertEqual(direction['palette'], 'gold and indigo')
            self.assertEqual(direction['medium'], 'oil painting')
            self.assertNotIn('empty background', direction['composition'])
            self.assertIn(direction['richness'], render.call_args.args[0])
            self.assertIn('full-bleed', render.call_args.args[0])
            self.assertEqual(direction['richness'], art.SCENE_PROFILES[direction['composition']])
            self.assertEqual(direction['approach'], 'a lantern')
            art.cover_for(track)
            self.assertEqual(len(render.call_args_list), 2)
            self.assertEqual(render.call_args.args[0], render.call_args_list[0].args[0])

    def test_scene_richness_varies_with_composition_instead_of_defaulting_to_minimal(self):
        director = art.ArtDirector(random.Random(42))
        directions = [director.choose('synthwave') for _ in range(10)]
        self.assertTrue(all(d.get('richness') for d in directions))
        self.assertEqual(len({d['richness'] for d in directions}), 10)
        self.assertGreaterEqual(sum('layered' in d['richness'].lower() for d in directions), 7)
        self.assertTrue(any('graphic' in d['composition'].lower() for d in directions))
        self.assertTrue(any('cinematic' in d['composition'].lower() for d in directions))

    def test_session_and_library_receive_the_original_art_brief(self):
        spec = songs.normalize({'title': 'Paper Lanterns', 'cover_prompt': 'A paper lantern floating on a pond'}, {'genre': 'synthwave', 'vocals': False})
        spec['art_direction'] = art.ArtDirector(random.Random(5)).choose('synthwave')
        opts = {'genre': 'synthwave', 'tracks': 1, 'custom_single': True}
        sid = 'arttest'
        with tempfile.TemporaryDirectory() as temp, patch.object(jukebox, 'SESSIONS_DIR', Path(temp)), patch.dict(jukebox._sessions, {sid: {'progress': {}}}, clear=True), patch.object(songs, 'compose_track', return_value=spec), patch.object(jukebox, '_generate_song', return_value=(b'test-audio', {})), patch.object(art, 'cover_for', return_value=b'test-cover'), patch.object(jukebox.library_mod, 'add') as add:
            (Path(temp) / sid).mkdir()
            jukebox._build(sid, opts, 1)
            session = jukebox.get(sid)
            assert session is not None
            self.assertEqual(session['state'], 'ready')
            track = session['manifest']['tracks'][0]
            self.assertEqual(track.get('art_direction'), spec['art_direction'])
            self.assertEqual(track.get('cover_prompt'), spec['cover_prompt'])
            self.assertEqual(add.call_args.args[0]['art_direction'], spec['art_direction'])

    def test_renderer_uses_visual_direction_even_when_cover_prompt_is_missing(self):
        track: dict = {'title': 'Paper Lanterns', 'caption': 'Dreamy synthesizer pulses', 'genres': 'synthwave'}
        with patch.object(art, 'generate_cover_art', return_value=b'test-image') as render:
            self.assertEqual(art.cover_for(track), b'test-image')
            first_prompt = render.call_args.args[0]
            self.assertTrue(track.get('art_direction'))
            for value in track['art_direction'].values():
                self.assertIn(value, first_prompt)
            self.assertIn('Paper Lanterns', first_prompt)
            self.assertIn('No text', first_prompt)
            art.cover_for(track)
            self.assertEqual(render.call_args.args[0], first_prompt)

    def test_composer_receives_and_retains_the_assigned_visual_brief(self):
        direction = art.ArtDirector(random.Random(3)).choose('synthwave')
        with patch.object(songs.naming, 'director', songs.naming.NamingDirector(history=lambda: [])), patch.object(art.director, 'choose', return_value=direction), patch.object(songs, 'chat_json', return_value={'title': 'Paper Lanterns', 'artist': 'Maren Quill', 'caption': 'Bright synthesizer arpeggios'}) as chat:
            track = songs.compose_track({'genre': 'synthwave', 'theme': 'Paper lanterns', 'vocals': False})
        self.assertEqual(track.get('art_direction'), direction)
        prompt = chat.call_args.args[1]
        for value in direction.values():
            self.assertIn(value, prompt)
        self.assertIn('Paper lanterns', prompt)
        self.assertEqual(track['caption'], 'Bright synthesizer arpeggios')

    def test_same_genre_gets_distinct_palettes_media_and_layouts(self):
        director = art.ArtDirector(random.Random(42))
        directions = [director.choose('synthwave') for _ in range(8)]
        for dimension in ('palette', 'medium', 'composition', 'approach'):
            self.assertEqual(len({d[dimension] for d in directions}), 8, dimension)
        self.assertLessEqual(sum('magenta' in d['palette'] for d in directions), 1)

    def test_interleaved_genres_keep_their_own_nonrepeating_history(self):
        director = art.ArtDirector(random.Random(41))
        first = [director.choose('synthwave') for _ in range(4)]
        other = [director.choose('jazz') for _ in range(4)]
        rest = [director.choose(' SYNTHWAVE ') for _ in range(4)]
        for dimension in ('palette', 'medium', 'composition', 'approach'):
            self.assertEqual(len({d[dimension] for d in first + rest}), 8)
        self.assertNotEqual([d['palette'] for d in first], [d['palette'] for d in other])

    def test_shuffle_boundaries_do_not_repeat_the_last_value(self):
        director = art.ArtDirector(random.Random(2))
        directions = [director.choose('rock') for _ in range(100)]
        for prev, current in zip(directions, directions[1:]):
            for dimension in current:
                self.assertNotEqual(prev[dimension], current[dimension])

    def test_parallel_requests_do_not_duplicate_first_batch_directions(self):
        director = art.ArtDirector(random.Random(4))
        with ThreadPoolExecutor(max_workers=8) as pool:
            directions = list(pool.map(director.choose, ['synthwave'] * 8))
        for dimension in directions[0]:
            self.assertEqual(len({d[dimension] for d in directions}), 8)


if __name__ == '__main__':
    unittest.main()
