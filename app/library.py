"""Persistent track library.

Every generated song is added to the library (rubric: "generate playable
audio ... and add it to the library"). Tracks keep their own audio + cover
copies under ``library/tracks/<id>/`` and a JSON index (``library/tracks.json``),
so they survive restarts and are browsable/playable independently of the
jam session that produced them. The whole ``library/`` tree is gitignored —
it is generated content, never part of a submission.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger("aijukebox.library")

LIBRARY_DIR = Path(__file__).resolve().parent.parent / "library"
TRACKS_DIR = LIBRARY_DIR / "tracks"
INDEX_PATH = LIBRARY_DIR / "tracks.json"

LIBRARY_DIR.mkdir(exist_ok=True)
TRACKS_DIR.mkdir(exist_ok=True)
if not INDEX_PATH.exists():
    INDEX_PATH.write_text("[]", encoding="utf-8")

_lock = threading.Lock()


def add(track: dict, audio_path: Path, art_path: Path | None, *,
        session_id: str, options: dict | None = None) -> dict:
    """Copy a generated song into the library and append it to the index."""
    options = options or {}
    track_id = uuid.uuid4().hex[:8]
    tdir = TRACKS_DIR / track_id
    tdir.mkdir(parents=True, exist_ok=True)

    audio_dst = tdir / "audio.mp3"
    shutil.copyfile(audio_path, audio_dst)

    has_art = art_path is not None and art_path.exists()
    art_dst = tdir / "cover.png"
    if has_art:
        shutil.copyfile(art_path, art_dst)

    lyrics = track.get("lyrics") or ""
    meta = track.get("meta") or {}
    entry = {
        "id": track_id,
        "title": track.get("title", "Untitled"),
        "artist": track.get("artist", ""),
        "genre": track.get("genres") or meta.get("genres") or "",
        "set_genre": options.get("genre", ""),
        "mood": options.get("mood", ""),
        "bpm": track.get("bpm") or meta.get("bpm"),
        "key_scale": track.get("key_scale") or meta.get("key_scale") or "",
        "duration_sec": meta.get("duration"),
        "vocals": bool(lyrics),
        "lyrics": lyrics,
        "seed": meta.get("seed", ""),
        "audio_url": f"/library/tracks/{track_id}/audio.mp3",
        "art_url": f"/library/tracks/{track_id}/cover.png" if has_art else "",
        "source_session": session_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _lock:
        index = _read_index_locked()
        index.insert(0, entry)
        _write_index_locked(index)
    log.info("library track added: %s — %s (%s)", entry["title"], entry["artist"], track_id)
    return entry


def list_tracks() -> list[dict]:
    with _lock:
        return _read_index_locked()


def _read_index_locked() -> list[dict]:
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 - a corrupt index is not fatal
        log.warning("library index unreadable; starting fresh")
        return []


def _write_index_locked(index: list[dict]) -> None:
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
    tmp.replace(INDEX_PATH)  # atomic-ish on POSIX + Windows
