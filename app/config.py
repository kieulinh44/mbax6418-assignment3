"""Central configuration for the AI Jukebox.

Every value can be overridden via environment variables (or a local ``.env``
file), so the app runs anywhere with the same class credentials. The defaults
point at the MBAX 6418 class endpoints that were verified for this assignment.
"""
from __future__ import annotations

import os

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# --- Class services (verified against live endpoints) -------------------------
CHAT_BASE_URL = os.environ.get("AIJ_CHAT_BASE_URL", "http://dobolyi.com:9001/v1")
CHAT_MODEL    = os.environ.get("AIJ_CHAT_MODEL", "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit")

ART_BASE_URL  = os.environ.get("AIJ_ART_BASE_URL", "http://dobolyi.com:9006/v1")
ART_MODEL     = os.environ.get("AIJ_ART_MODEL", "black-forest-labs/FLUX.2-klein-4B")

MUSIC_BASE_URL = os.environ.get("AIJ_MUSIC_BASE_URL", "http://dobolyi.com:9007")
MUSIC_MODEL    = os.environ.get("AIJ_MUSIC_MODEL", "acestep-v15-xl-turbo")  # server default DiT
MUSIC_LM_MODEL = os.environ.get("AIJ_MUSIC_LM_MODEL", "acestep-5Hz-lm-4B")

TTS_BASE_URL  = os.environ.get("AIJ_TTS_BASE_URL", "http://dobolyi.com:9008/v1")
TTS_MODEL     = os.environ.get("AIJ_TTS_MODEL", "chatterbox-v3")
TTS_VOICE     = os.environ.get("AIJ_TTS_VOICE", "default")

# Credentials are read from the environment / a local .env file ONLY.
# Never hardcode, commit, log, or document real keys — see .env.example
# and the README's "Credentials & safeguards" section.
API_KEY = os.environ.get("AIJ_API_KEY", "")

# --- Generation defaults (safe, quick, demo-friendly) -------------------------
DEFAULT_DURATION = 30   # seconds per song (ACE-Step allows 10-600)
DEFAULT_TRACKS = 3
MAX_TRACKS = 8
MAX_DURATION = 120      # UI cap (ACE-Step allows up to 600)

GENRES = [
    "synthwave", "pop", "rock", "lo-fi", "bossanova", "hip-hop",
    "electronic", "jazz", "country", "reggaeton", "metal", "ambient",
]
MOODS = ["energetic", "chill", "happy", "melancholic", "epic", "dreamy"]
