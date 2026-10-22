import logging
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, load_settings


class ConfigLoadingTests(unittest.TestCase):
    def write_env(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / ".env"
        path.write_text(text)
        self.addCleanup(lambda: __import__("shutil").rmtree(directory))
        return path

    def test_values_load_from_dotenv(self):
        path = self.write_env(
            "AIJ_API_KEY=file-only-secret\n"
            "AIJ_CHAT_BASE_URL=https://file.example.test/chat\n"
        )
        settings = load_settings(dotenv_path=path, environ={})
        self.assertEqual(settings["AIJ_API_KEY"], "file-only-secret")
        self.assertEqual(settings["AIJ_CHAT_BASE_URL"], "https://file.example.test/chat")

    def test_explicit_environment_overrides_dotenv(self):
        path = self.write_env(
            "AIJ_API_KEY=file-secret\n"
            "AIJ_CHAT_BASE_URL=https://file.example.test/chat\n"
        )
        settings = load_settings(
            dotenv_path=path,
            environ={
                "AIJ_API_KEY": "shell-secret",
                "AIJ_CHAT_BASE_URL": "https://shell.example.test/chat",
            },
        )
        self.assertEqual(settings["AIJ_API_KEY"], "shell-secret")
        self.assertEqual(settings["AIJ_CHAT_BASE_URL"], "https://shell.example.test/chat")

    def test_missing_required_key_is_actionable_without_secret_values(self):
        path = self.write_env("AIJ_CHAT_BASE_URL=https://file.example.test/chat\n")
        with self.assertRaises(ConfigError) as raised:
            load_settings(dotenv_path=path, environ={})
        message = str(raised.exception)
        self.assertIn("AIJ_API_KEY", message)
        self.assertIn(".env", message)
        self.assertNotIn("file.example.test", message)

    def test_malformed_url_is_rejected_without_echoing_the_url(self):
        secret_url = "not-a-url-with-sensitive-token"
        path = self.write_env(
            f"AIJ_API_KEY=safe-test-key\nAIJ_CHAT_BASE_URL={secret_url}\n"
        )
        with self.assertRaises(ConfigError) as raised:
            load_settings(dotenv_path=path, environ={})
        message = str(raised.exception)
        self.assertIn("AIJ_CHAT_BASE_URL", message)
        self.assertIn("http:// or https://", message)
        self.assertNotIn(secret_url, message)

    def test_secret_is_safe_if_configuration_error_is_logged(self):
        secret = "super-secret-test-value"
        path = self.write_env(
            f"AIJ_API_KEY={secret}\nAIJ_ART_BASE_URL=ftp://invalid.example\n"
        )
        with self.assertRaises(ConfigError) as raised:
            load_settings(dotenv_path=path, environ={})
        logger = logging.getLogger("config-test")
        rendered = str(raised.exception)
        logger.error("configuration rejected: %s", rendered)
        self.assertNotIn(secret, rendered)


if __name__ == "__main__":
    unittest.main()
