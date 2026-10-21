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
        self.assertEqual(self.page.get_by_role("progressbar").get_attribute("aria-valuenow"), "100")
        self.assertTrue(self.page.locator("#jam-btn").is_enabled())

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
        self.page.evaluate("renderLibrary([{title: 'Playback test', artist: 'Test artist', audio_url: '/ui-test.wav', lyrics: 'Test lyrics'}])")
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
        self.assertEqual(self.page.get_by_role("progressbar").get_attribute("aria-valuenow"), "50")
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
        self.page.evaluate("renderLibrary([{title: 'Test record', artist: 'Test artist', bpm: 110, vocals: true}])")
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

    def test_creation_and_playback_have_named_landmarks(self):
        self.assertEqual(self.page.get_by_role("heading", name="Create your record", exact=True).count(), 1)
        self.assertEqual(self.page.get_by_role("region", name="Record player", exact=True).count(), 1)
        self.assertEqual(self.page.get_by_role("region", name="Your collection", exact=True).count(), 1)
        self.assertEqual(self.page.locator("#deck-status").get_attribute("role"), "status")
        self.assertEqual(self.page.get_by_label("Genre", exact=True).input_value(), "synthwave")
        self.assertTrue(self.page.get_by_role("button", name="Start the jam", exact=False).is_visible())


if __name__ == "__main__":
    unittest.main()
