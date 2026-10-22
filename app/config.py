"""Validated configuration for the AI Jukebox.

Configuration is loaded from a root-level ``.env`` file first, then explicit
process environment variables are applied on top. This gives shell exports
precedence without requiring users to source the file manually.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = ROOT_DIR / ".env"

DEFAULTS = {
    "AIJ_CHAT_BASE_URL": "http://dobolyi.com:9001/v1",
    "AIJ_CHAT_MODEL": "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
    "AIJ_ART_BASE_URL": "http://dobolyi.com:9006/v1",
    "AIJ_ART_MODEL": "black-forest-labs/FLUX.2-klein-4B",
    "AIJ_MUSIC_BASE_URL": "http://dobolyi.com:9007",
    "AIJ_MUSIC_MODEL": "acestep-v15-xl-turbo",
    "AIJ_MUSIC_LM_MODEL": "acestep-5Hz-lm-4B",
    "AIJ_TTS_BASE_URL": "http://dobolyi.com:9008/v1",
    "AIJ_TTS_MODEL": "chatterbox-v3",
    "AIJ_TTS_VOICE": "default",
    "AIJ_PORT": "8000",
}

URL_KEYS = (
    "AIJ_CHAT_BASE_URL",
    "AIJ_ART_BASE_URL",
    "AIJ_MUSIC_BASE_URL",
    "AIJ_TTS_BASE_URL",
)


class ConfigError(ValueError):
    """Actionable configuration error that never includes secret values."""


def _merged_values(dotenv_path: Path | str | None, environ: Mapping[str, str] | None) -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path(dotenv_path) if dotenv_path else None
    if path and path.is_file():
        values.update({key: value for key, value in dotenv_values(path).items() if value is not None})
    # Explicit environment values always win over values loaded from .env.
    values.update(dict(os.environ if environ is None else environ))
    return values


def validate_settings(settings: Mapping[str, str]) -> None:
    errors: list[str] = []
    if not str(settings.get("AIJ_API_KEY", "")).strip():
        errors.append("AIJ_API_KEY is required; set it in .env or export it in the shell")

    for key in URL_KEYS:
        value = str(settings.get(key, "")).strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            errors.append(f"{key} must begin with http:// or https://")

    try:
        port = int(str(settings.get("AIJ_PORT", "8000")))
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("AIJ_PORT must be an integer between 1 and 65535")

    if errors:
        raise ConfigError("Configuration invalid: " + "; ".join(errors))


def load_settings(
    dotenv_path: Path | str | None = DOTENV_PATH,
    environ: Mapping[str, str] | None = None,
    *,
    validate: bool = True,
) -> dict[str, str]:
    """Load settings from .env plus environment variables.

    ``environ`` is injectable for tests. Real process environment variables
    override the dotenv values by design.
    """
    values = {**DEFAULTS, **_merged_values(dotenv_path, environ)}
    if validate:
        validate_settings(values)
    return values


# Keep import-time constants available to the rest of the app. Startup calls
# validate_config() so missing or malformed values fail with an actionable error.
_SETTINGS = load_settings(validate=False)
CHAT_BASE_URL = _SETTINGS["AIJ_CHAT_BASE_URL"].strip()
CHAT_MODEL = _SETTINGS["AIJ_CHAT_MODEL"].strip()
ART_BASE_URL = _SETTINGS["AIJ_ART_BASE_URL"].strip()
ART_MODEL = _SETTINGS["AIJ_ART_MODEL"].strip()
MUSIC_BASE_URL = _SETTINGS["AIJ_MUSIC_BASE_URL"].strip()
MUSIC_MODEL = _SETTINGS["AIJ_MUSIC_MODEL"].strip()
MUSIC_LM_MODEL = _SETTINGS["AIJ_MUSIC_LM_MODEL"].strip()
TTS_BASE_URL = _SETTINGS["AIJ_TTS_BASE_URL"].strip()
TTS_MODEL = _SETTINGS["AIJ_TTS_MODEL"].strip()
TTS_VOICE = _SETTINGS["AIJ_TTS_VOICE"].strip()
API_KEY = _SETTINGS.get("AIJ_API_KEY", "").strip()
try:
    PORT = int(_SETTINGS.get("AIJ_PORT", "8000"))
except (TypeError, ValueError):
    PORT = 8000


def validate_config() -> dict[str, str]:
    """Validate the startup configuration without exposing secret values."""
    settings = load_settings()
    validate_settings(settings)
    return settings


# --- Generation defaults (safe, quick, demo-friendly) -------------------------
MIN_VOCAL_DURATION = 60
DEFAULT_DURATION = 60
DEFAULT_TRACKS = 3
MAX_TRACKS = 8
MAX_DURATION = 120

GENRES = [
    "synthwave", "pop", "rock", "lo-fi", "bossanova", "hip-hop",
    "electronic", "jazz", "country", "reggaeton", "metal", "ambient",
]
MOODS = ["energetic", "chill", "happy", "melancholic", "epic", "dreamy"]
