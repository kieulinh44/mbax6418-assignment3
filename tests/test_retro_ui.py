"""Browser regression checks. Run against AIJ_TEST_URL (default port 8003).

Install development tools: uv pip install --python .venv/bin/python -r requirements-dev.txt
Then: .venv/bin/python -m playwright install chromium
Run: .venv/bin/python -m unittest discover -s tests -v
"""
import os
import unittest
import io
import wave

from playwright.sync_api import expect, sync_playwright


class RetroInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1100})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/api/library", lambda route: route.fulfill(json={"tracks": []}))
        self.page.route("**/api/health", lambda route: route.fulfill(json={"services": [{"name": name, "model": "ui-test", "ok": True} for name in ("Qwen · text", "FLUX · art", "ACE-Step · music", "Chatterbox · DJ")]}))
        self.page.goto(os.environ.get("AIJ_TEST_URL", "http://127.0.0.1:8003"))
        self.page.locator("#genre option").first.wait_for(state="attached")
        self.page.locator("#library-list li").first.wait_for(state="attached")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def test_single_song_ready_state_and_request(self):
        captured = []
        self.page.route("**/api/custom-song", lambda route: (captured.append(route.request.post_data_json), route.fulfill(json={"id": "single-ui-test"})))
        self.page.route("**/api/session/single-ui-test", lambda route: route.fulfill(json={"state": "ready", "progress": {"done": 2, "total": 2}, "manifest": {"playlist": [{"kind": "song", "title": "UI test record", "artist": "UI test artist", "audio": "/ui-test.wav"}]}}))
        self.page.locator("#theme").fill("A test theme")
        self.page.locator("#vocals").uncheck()
        self.page.locator("#single-btn").click()
        expect(self.page.locator("#play-btn")).to_be_visible()
        self.assertEqual(captured[0]["tracks"], 1)
        self.assertEqual(captured[0]["theme"], "A test theme")
        self.assertFalse(captured[0]["vocals"])
        self.assertEqual(self.page.locator("#queue li").count(), 1)
        self.assertEqual(self.page.get_by_role("slider", name="Seek playback position").get_attribute("aria-valuenow"), "100")
        self.assertTrue(self.page.locator("#jam-btn").is_enabled())

    def test_vocals_have_visible_duration_floor_and_instrumentals_allow_short_clips(self):
        expect(self.page.locator('#duration')).to_have_attribute('min', '60')
        expect(self.page.locator('#duration')).to_have_value('60')
        expect(self.page.locator('#duration-help')).to_contain_text('at least 60 seconds')
        self.page.locator('#vocals').uncheck()
        expect(self.page.locator('#duration')).to_have_attribute('min', '10')
        self.page.locator('#duration').fill('10')
        self.page.locator('#duration').dispatch_event('input')
        expect(self.page.locator('#duration-val')).to_have_text('10s')
        self.page.locator('#vocals').check()
        expect(self.page.locator('#duration')).to_have_value('60')
        expect(self.page.locator('#duration-val')).to_have_text('60s')

    def test_generation_error_recovers_controls(self):
        self.page.route("**/api/custom-song", lambda route: route.fulfill(json={"id": "error-ui-test"}))
        self.page.route("**/api/session/error-ui-test", lambda route: route.fulfill(json={"state": "error", "error": "Service temporarily unavailable", "progress": {"done": 0, "total": 1}}))
        self.page.locator("#single-btn").click()
        expect(self.page.locator("#deck-status")).to_contain_text("Generation failed")
        self.assertTrue(self.page.locator("#jam-btn").is_enabled())
        self.assertTrue(self.page.locator("#single-btn").is_enabled())

    def test_both_themes_fit_mobile_tablet_and_desktop(self):
        for theme in ("dark", "light"):
            for width in (320, 390, 740, 1024, 1440):
                with self.subTest(theme=theme, width=width):
                    self.page.set_viewport_size({"width": width, "height": 1000})
                    self.page.evaluate("theme => applyTheme(theme)", theme)
                    self.assertFalse(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                    for selector in ("#jam-btn", "#single-btn", "#theme-toggle", "#genre", "#mood", "#dj"):
                        box = self.page.locator(selector).bounding_box()
                        assert box is not None
                        self.assertGreaterEqual(box["height"], 44)

    def test_keyboard_skip_link_and_reduced_motion(self):
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.locator(":focus").inner_text(), "Skip to controls")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.locator(":focus").get_attribute("id"), "create")
        self.page.emulate_media(reduced_motion="reduce")
        self.page.locator("#vinyl").evaluate("el => el.classList.add('spin')")
        self.assertEqual(self.page.locator("#vinyl").evaluate("el => getComputedStyle(el).animationName"), "none")

    def test_playback_pause_resume_and_end_states(self):
        # A real, silent WAV fixture exercises HTML audio without remote AI calls.
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\0\0" * 8000 * 10)
        self.page.route("**/ui-test.wav", lambda route: route.fulfill(body=audio.getvalue(), content_type="audio/wav"))
        self.page.evaluate("renderLibrary([{id: 'abcdef12', title: 'Playback test', artist: 'Test artist', audio_url: '/ui-test.wav', lyrics: 'Test lyrics'}])")
        self.page.get_by_role("button", name="Play Playback test", exact=True).click()
        self.page.wait_for_function("!document.querySelector('#player').paused && document.querySelector('#player').currentTime > 0")
        self.page.get_by_role("button", name="Pause playback", exact=True).click()
        self.assertTrue(self.page.locator("#player").evaluate("el => el.paused"))
        expect(self.page.get_by_role("button", name="Resume playback", exact=True)).to_be_visible()
        self.assertNotIn("spin", self.page.locator("#vinyl").get_attribute("class") or "")
        self.page.get_by_role("button", name="Resume playback", exact=True).click()
        self.page.wait_for_function("!document.querySelector('#player').paused")
        expect(self.page.get_by_role("button", name="Pause playback", exact=True)).to_be_visible()
        self.assertIn("spin", self.page.locator("#vinyl").get_attribute("class") or "")
        self.page.locator("#player").evaluate("el => el.currentTime = el.duration - 0.1")
        self.page.wait_for_function("document.querySelector('#pause-btn').hidden")
        self.assertNotIn("spin", self.page.locator("#vinyl").get_attribute("class") or "")
        self.assertTrue(self.page.locator("#lyrics-box").is_visible())

    def test_generation_progress_is_accessible(self):
        self.page.route("**/api/session/ui-progress", lambda route: route.fulfill(json={"state": "building", "progress": {"done": 2, "total": 4, "stage": "Painting cover art"}}))
        self.page.evaluate("session.id = 'ui-progress'; poll()")
        self.assertEqual(self.page.get_by_role("slider", name="Seek playback position").get_attribute("aria-valuenow"), "50")
        self.assertIn("Painting cover art", self.page.locator("#deck-status").inner_text())

    def test_service_health_has_text_not_just_color(self):
        self.page.route("**/api/health", lambda route: route.fulfill(json={"services": [{"name": "Qwen · text", "model": "test", "ok": True}, {"name": "FLUX · art", "model": "test", "ok": False}]}))
        self.page.evaluate("health()")
        self.assertEqual(self.page.get_by_label("Composer: connected", exact=True).count(), 1)
        self.assertEqual(self.page.get_by_label("Cover art: unavailable", exact=True).count(), 1)

    def test_theme_switch_is_named_and_persists(self):
        self.page.evaluate("localStorage.setItem('aij-theme', 'dark')")
        self.page.reload()
        self.page.get_by_role("button", name="Switch to light mode").click()
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "light")
        self.page.reload()
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "light")
        self.assertTrue(self.page.get_by_role("button", name="Switch to dark mode").is_visible())

    def test_collection_play_buttons_identify_the_song(self):
        self.page.evaluate("renderLibrary([{id: 'abcdef12', title: 'Test record', artist: 'Test artist', bpm: 110, vocals: true}])")
        button = self.page.get_by_role("button", name="Play Test record", exact=True)
        self.assertEqual(button.count(), 1)
        box = button.bounding_box()
        assert box is not None
        self.assertGreaterEqual(box["width"], 44)
        self.assertGreaterEqual(box["height"], 44)
        self.assertTrue(self.page.locator(".track-meta").is_visible())

    def test_jam_button_uses_full_set_endpoint(self):
        requests = []
        self.page.route("**/api/jam", lambda route: (requests.append(route.request), route.fulfill(status=200, json={"id": "ui-test"})))
        self.page.route("**/api/custom-song", lambda route: (requests.append(route.request), route.fulfill(status=200, json={"id": "ui-test"})))
        self.page.route("**/api/session/ui-test", lambda route: route.fulfill(json={"state": "building", "progress": {"stage": "Composing", "done": 1, "total": 4}}))
        self.page.locator("#jam-btn").click()
        self.page.wait_for_function("document.querySelector('#jam-btn').disabled")
        self.assertTrue(requests[0].url.endswith("/api/jam"))
        self.assertEqual(requests[0].post_data_json["tracks"], 3)
        self.assertTrue(self.page.locator("#single-btn").is_disabled())

    def collection_fixture(self):
        self.records = [{'id': 'abcdef12', 'title': 'Fixture record', 'artist': 'Fixture artist',
                         'audio_url': '/library/tracks/abcdef12/audio.mp3', 'lyrics': 'Fixture lyrics'}]
        self.deletes = []
        self.page.route('**/api/library', lambda route: route.fulfill(json={'tracks': self.records}))
        self.page.route('**/api/library/*', lambda route: (self.deletes.append(route.request.method), route.fulfill(status=500, json={'detail': 'Fixture disk error'})))
        self.page.evaluate('refreshLibrary()')

    def play_collection_fixture(self):
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b'\0\0' * 8000 * 30)
        self.page.route('**/library/tracks/*/audio.mp3', lambda route: route.fulfill(body=audio.getvalue(), content_type='audio/wav'))
        self.page.route('**/sessions/original/audio.mp3', lambda route: route.fulfill(body=audio.getvalue(), content_type='audio/wav'))
        self.page.get_by_role('button', name='Play Fixture record', exact=True).click()
        self.page.wait_for_function('!player.paused && player.currentTime > 0')

    def confirm_fixture_success(self):
        def delete(route):
            self.records.clear()
            route.fulfill(json={'removed': 'abcdef12'})
        self.page.route('**/api/library/abcdef12', delete)
        self.page.get_by_role('button', name='Remove Fixture record', exact=True).click()
        self.page.get_by_role('button', name='Remove song', exact=True).click()
        expect(self.page.get_by_role('dialog')).not_to_be_visible()

    def test_remove_confirmation_cancel_is_safe_and_keyboard_accessible(self):
        self.collection_fixture()
        remove = self.page.get_by_role('button', name='Remove Fixture record', exact=True)
        remove.click()
        dialog = self.page.get_by_role('dialog', name='Remove from collection?')
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text('Fixture record')
        expect(dialog).to_contain_text('Original session files are kept')
        expect(dialog.get_by_role('button', name='Cancel', exact=True)).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(dialog).not_to_be_visible()
        expect(remove).to_be_focused()
        remove.click()
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        expect(dialog).not_to_be_visible()
        self.assertEqual(self.deletes, [])
        expect(self.page.locator('#library-list')).to_contain_text('Fixture record')

    def test_remove_success_waits_for_server_then_updates_empty_state(self):
        self.collection_fixture()
        held = []
        self.page.route('**/api/library/abcdef12', lambda route: held.append(route))
        self.page.get_by_role('button', name='Remove Fixture record', exact=True).click()
        self.page.get_by_role('button', name='Remove song', exact=True).click()
        expect(self.page.locator('#library-list')).to_contain_text('Fixture record')
        expect(self.page.get_by_role('button', name='Remove song', exact=True)).to_be_disabled()
        self.assertEqual(held[0].request.method, 'DELETE')
        self.records.clear()
        held[0].fulfill(json={'removed': 'abcdef12'})
        expect(self.page.get_by_role('dialog')).not_to_be_visible()
        expect(self.page.locator('#library-list')).to_contain_text('No songs yet')
        expect(self.page.locator('#library-count')).to_have_text('')
        expect(self.page.locator('#library-status')).to_contain_text('Removed “Fixture record”')
        expect(self.page.locator('#collection-heading')).to_be_focused()

    def test_remove_error_keeps_song_and_allows_retry_or_cancel(self):
        self.collection_fixture()
        self.play_collection_fixture()
        self.page.get_by_role('button', name='Remove Fixture record', exact=True).click()
        self.page.get_by_role('button', name='Remove song', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role('status')).to_contain_text('Fixture disk error')
        expect(self.page.locator('#library-list')).to_contain_text('Fixture record')
        expect(self.page.locator('#library-count')).to_have_text('(1)')
        expect(dialog.get_by_role('button', name='Remove song', exact=True)).to_be_enabled()
        expect(dialog.get_by_role('button', name='Cancel', exact=True)).to_be_enabled()
        self.assertEqual(self.deletes, ['DELETE'])
        self.assertFalse(self.page.locator('#player').evaluate('el => el.paused'))
        expect(self.page.locator('#title')).to_have_text('Fixture record')
        dialog.get_by_role('button', name='Cancel', exact=True).click()

    def test_remove_current_library_audio_resets_the_player(self):
        self.collection_fixture()
        self.play_collection_fixture()
        self.page.evaluate('setProgress(35)')
        self.confirm_fixture_success()
        player = self.page.locator('#player')
        self.assertTrue(player.evaluate('el => el.paused'))
        self.assertIsNone(player.get_attribute('src'))
        expect(self.page.locator('#pause-btn')).not_to_be_visible()
        expect(self.page.locator('#play-btn')).not_to_be_visible()
        expect(self.page.locator('#seek-dot')).not_to_be_visible()
        expect(self.page.locator('#previous-btn')).to_be_disabled()
        expect(self.page.locator('#next-btn')).to_be_disabled()
        expect(self.page.locator('#title')).to_have_text('Good things are about to spin.')
        expect(self.page.locator('#kind')).to_have_text('READY WHEN YOU ARE')
        expect(self.page.locator('#lyrics-box')).not_to_be_visible()
        self.assertIsNone(self.page.locator('#art').get_attribute('src'))
        self.assertNotIn('spin', self.page.locator('#vinyl').get_attribute('class') or '')
        self.assertEqual(self.page.get_by_role('slider', name='Seek playback position').get_attribute('aria-valuenow'), '0')

    def test_remove_unrelated_library_or_original_session_does_not_stop_playback(self):
        for source in ('/library/tracks/1234abcd/audio.mp3', '/sessions/original/audio.mp3'):
            with self.subTest(source=source):
                self.collection_fixture()
                self.play_collection_fixture()
                self.page.evaluate("source => { session.manifest = {playlist: [{audio: source}]}; session.idx = 0; player.src = source; player.play(); }", source)
                self.page.wait_for_function('!player.paused && player.currentTime > 0')
                self.confirm_fixture_success()
                self.assertEqual(self.page.locator('#player').get_attribute('src'), source)
                self.assertFalse(self.page.locator('#player').evaluate('el => el.paused'))
                self.assertEqual(self.page.evaluate('session.idx'), 0)
                self.assertIsNotNone(self.page.evaluate('session.manifest'))
                expect(self.page.locator('#pause-btn')).to_be_visible()

    def test_remove_one_of_two_updates_count_and_retains_other_song(self):
        self.collection_fixture()
        other = {**self.records[0], 'id': '1234abcd', 'title': 'Keep this record'}
        self.records.append(other)
        self.page.evaluate('refreshLibrary()')
        def delete(route):
            self.records[:] = [other]
            route.fulfill(json={'removed': 'abcdef12'})
        self.page.route('**/api/library/abcdef12', delete)
        self.page.get_by_role('button', name='Remove Fixture record', exact=True).click()
        self.page.get_by_role('button', name='Remove song', exact=True).click()
        expect(self.page.locator('#library-count')).to_have_text('(1)')
        expect(self.page.locator('#library-list')).to_contain_text('Keep this record')
        expect(self.page.locator('#library-list')).not_to_contain_text('Fixture record')

    def test_remove_controls_and_themed_dialog_fit_mobile_without_overflow(self):
        self.collection_fixture()
        for theme in ('dark', 'light'):
            for width in (320, 390, 740, 1440):
                with self.subTest(theme=theme, width=width):
                    self.page.set_viewport_size({'width': width, 'height': 1000})
                    self.page.evaluate('theme => applyTheme(theme)', theme)
                    remove = self.page.get_by_role('button', name='Remove Fixture record', exact=True)
                    box = remove.bounding_box()
                    row = self.page.locator('#library-list li').bounding_box()
                    assert box and row
                    self.assertGreaterEqual(box['height'], 44)
                    self.assertLessEqual(box['x'] + box['width'], row['x'] + row['width'])
                    remove.click()
                    dialog = self.page.get_by_role('dialog')
                    self.assertTrue(dialog.evaluate("el => getComputedStyle(el).backgroundColor === getComputedStyle(document.querySelector('.panel')).backgroundColor"))
                    self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    self.assertFalse(dialog.evaluate('el => el.scrollWidth > el.clientWidth'))
                    dialog.get_by_role('button', name='Cancel', exact=True).click()

    def segment_fixture(self):
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b'\0\0' * 8000 * 20)
        def serve_audio(route):
            body = audio.getvalue()
            requested = route.request.headers.get('range')
            if requested:
                start, end = requested.removeprefix('bytes=').split('-')
                start, end = int(start), int(end) if end else len(body) - 1
                route.fulfill(status=206, body=body[start:end + 1], content_type='audio/wav',
                              headers={'Accept-Ranges': 'bytes', 'Content-Range': f'bytes {start}-{end}/{len(body)}'})
            else:
                route.fulfill(body=body, content_type='audio/wav', headers={'Accept-Ranges': 'bytes'})
        self.page.route('**/segment-*.wav', serve_audio)
        self.page.evaluate("""() => {
            session.manifest = {playlist: [
                {kind: 'intro', title: 'DJ welcome', audio: '/segment-0.wav'},
                {kind: 'song', title: 'First song', artist: 'Artist', lyrics: 'Song lyrics', art: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>', audio: '/segment-1.wav'},
                {kind: 'interlude', title: 'DJ break', audio: '/segment-2.wav'}
            ]};
            renderQueue(session.manifest.playlist); playSet();
        }""")
        self.page.wait_for_function('!player.paused && player.currentTime > 0')

    def test_previous_next_step_songs_and_dj_without_wrapping(self):
        self.segment_fixture()
        previous = self.page.get_by_role('button', name='Previous segment', exact=True)
        following = self.page.get_by_role('button', name='Next segment', exact=True)
        expect(previous).to_be_disabled()
        following.click()
        expect(self.page.locator('#title')).to_have_text('First song')
        expect(self.page.locator('#lyrics-text')).to_have_text('Song lyrics')
        expect(self.page.locator('#art')).to_have_class('show')
        self.page.get_by_role('button', name='Pause playback', exact=True).click()
        following.click()  # Selection plays, consistently with a playbill row.
        self.page.wait_for_function('!player.paused && player.currentTime > 0')
        expect(self.page.locator('#title')).to_have_text('DJ break')
        expect(self.page.locator('#lyrics-box')).not_to_be_visible()
        self.assertIsNone(self.page.locator('#art').get_attribute('src'))
        expect(following).to_be_disabled()
        previous.click()
        expect(self.page.locator('#title')).to_have_text('First song')
        self.assertLess(self.page.locator('#player').evaluate('el => el.currentTime'), 2)
        previous.click()
        expect(self.page.locator('#title')).to_have_text('DJ welcome')
        expect(previous).to_be_disabled()
        for theme in ('light', 'dark'):
            self.page.evaluate('theme => applyTheme(theme)', theme)
            self.page.set_viewport_size({'width': 320, 'height': 1000})
            for button in (previous, following):
                box = button.bounding_box()
                assert box is not None
                self.assertGreaterEqual(box['width'], 44)
                self.assertGreaterEqual(box['height'], 44)
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.evaluate('jumpTo(2)')
        self.page.wait_for_function('!player.paused && player.readyState === 4 && player.seekable.length && player.seekable.end(0) === player.duration && player.currentSrc.endsWith("segment-2.wav")')
        self.page.locator('#player').evaluate('el => el.currentTime = el.duration - 0.1')
        expect(self.page.locator('#deck-status')).to_contain_text('Set finished')
        expect(following).to_be_disabled()
        previous.click()
        expect(self.page.locator('#title')).to_have_text('First song')
        self.page.evaluate("playLibraryTrack({title: 'Lone record', audio_url: '/segment-1.wav'})")
        expect(previous).to_be_disabled()
        expect(following).to_be_disabled()
        self.page.evaluate('jumpTo(0)')
        expect(self.page.locator('#title')).to_have_text('Lone record')

    def test_seek_dot_tracks_real_audio_click_and_keyboard_not_generation(self):
        dot = self.page.locator('#seek-dot')
        expect(dot).not_to_be_visible()
        self.page.evaluate('setProgress(75)')
        expect(dot).not_to_be_visible()
        self.segment_fixture()
        expect(dot).to_be_visible()
        self.page.wait_for_function('player.currentTime > 0.5')
        start = dot.bounding_box()['x']
        self.page.wait_for_function('player.currentTime > 1.5')
        self.assertGreater(dot.bounding_box()['x'], start)
        slider = self.page.get_by_role('slider', name='Seek playback position')
        box = slider.bounding_box()
        slider.click(position={'x': box['width'] * .5, 'y': box['height'] / 2})
        self.page.wait_for_function('player.currentTime >= 9 && player.currentTime < 12')
        self.assertAlmostEqual(dot.bounding_box()['x'] + dot.bounding_box()['width'] / 2,
                               box['x'] + box['width'] / 2, delta=5)
        slider.focus()
        slider.press('ArrowLeft')
        self.assertLess(self.page.locator('#player').evaluate('el => el.currentTime'), 10)
        slider.press('Home')
        self.assertLess(self.page.locator('#player').evaluate('el => el.currentTime'), 1)
        self.assertGreaterEqual(dot.bounding_box()['x'], box['x'])
        self.page.evaluate('jumpTo(2)')
        self.page.wait_for_function('player.currentSrc.endsWith("segment-2.wav") && player.readyState === 4')
        slider.press('End')
        expect(self.page.locator('#deck-status')).to_contain_text('Set finished')
        self.assertLessEqual(dot.bounding_box()['x'] + dot.bounding_box()['width'], box['x'] + box['width'])
        self.page.evaluate('jumpTo(1)')
        self.page.wait_for_function('player.currentSrc.endsWith("segment-1.wav") && player.readyState === 4')
        self.assertLess(float(slider.get_attribute('aria-valuenow')), 5)
        self.page.route('**/api/custom-song', lambda route: route.fulfill(json={'id': 'dot-generation'}))
        self.page.route('**/api/session/dot-generation', lambda route: route.fulfill(json={'state': 'building', 'progress': {'done': 1, 'total': 2}}))
        self.page.locator('#single-btn').click()
        expect(dot).not_to_be_visible()
        expect(self.page.locator('#previous-btn')).to_be_disabled()
        expect(self.page.locator('#next-btn')).to_be_disabled()
        self.assertTrue(self.page.locator('#player').evaluate('el => el.paused'))
        expect(slider).to_have_attribute('aria-valuenow', '50')

    def test_collection_autoplay_fallback_has_only_one_resume_control(self):
        self.segment_fixture()
        self.page.evaluate("""() => {
            window.realPlay = player.play.bind(player);
            player.pause();
            player.play = () => Promise.reject(new DOMException('Blocked', 'NotAllowedError'));
            playLibraryTrack({title: 'Collection record', audio_url: '/segment-1.wav'});
        }""")
        expect(self.page.locator('#play-btn')).not_to_be_visible()
        resume = self.page.get_by_role('button', name='Resume playback', exact=True)
        expect(resume).to_be_visible()
        self.assertEqual(self.page.locator('button:visible').filter(has_text='Resume').count(), 1)
        expect(self.page.locator('#previous-btn')).to_be_disabled()
        expect(self.page.locator('#next-btn')).to_be_disabled()
        self.page.evaluate('() => { player.play = window.realPlay; }')
        resume.click()
        self.page.wait_for_function('!player.paused && player.currentTime > 0')
        expect(self.page.locator('#title')).to_have_text('Collection record')
        expect(self.page.get_by_role('button', name='Pause playback', exact=True)).to_be_visible()
        expect(self.page.locator('#play-btn')).not_to_be_visible()

    def test_autoplay_fallback_resumes_selection_and_ignores_stale_rejections(self):
        self.segment_fixture()
        self.page.evaluate("""() => {
            window.realPlay = player.play.bind(player);
            player.pause();
            player.play = () => Promise.reject(new DOMException('Blocked', 'NotAllowedError'));
        }""")
        self.page.locator('#next-btn').click()
        expect(self.page.locator('#play-btn')).not_to_be_visible()
        expect(self.page.locator('#pause-btn')).to_have_text('▶ Resume')
        expect(self.page.locator('#title')).to_have_text('First song')
        self.page.evaluate('() => { player.play = window.realPlay; }')
        self.page.get_by_role('button', name='Resume playback', exact=True).click()
        self.page.wait_for_function('!player.paused && player.currentTime > 0')
        self.assertEqual(self.page.evaluate('session.idx'), 1)
        self.page.evaluate("""() => {
            player.pause();
            player.play = () => new Promise((resolve, reject) => { window.rejectOldPlay = reject; });
            jumpTo(2);
            const rejectOld = window.rejectOldPlay;
            player.play = window.realPlay;
            playLibraryTrack({title: 'New selection', audio_url: '/segment-1.wav'});
            rejectOld(new DOMException('Superseded', 'AbortError'));
        }""")
        expect(self.page.locator('#play-btn')).not_to_be_visible()
        self.page.locator('#lyrics-box').evaluate('el => el.open = true')
        expect(self.page.locator('#lyrics-box')).to_contain_text('Lyric sheet · AI-sung repeats or wording may vary.')

    def test_creation_and_playback_have_named_landmarks(self):
        self.assertEqual(self.page.get_by_role("heading", name="Create your record", exact=True).count(), 1)
        self.assertEqual(self.page.get_by_role("region", name="Record player", exact=True).count(), 1)
        self.assertEqual(self.page.get_by_role("region", name="Your collection", exact=True).count(), 1)
        self.assertEqual(self.page.locator("#deck-status").get_attribute("role"), "status")
        self.assertEqual(self.page.get_by_label("Genre", exact=True).input_value(), "synthwave")
        self.assertTrue(self.page.get_by_role("button", name="Start the jam", exact=False).is_visible())


if __name__ == "__main__":
    unittest.main()
