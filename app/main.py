"""AI Jukebox - FastAPI entrypoint.

Run:  .venv/Scripts/python -m uvicorn app.main:app --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, djs, jukebox
from .clients import SESSION

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="AI Jukebox", version="0.1.0")

app.mount("/sessions", StaticFiles(directory=jukebox.SESSIONS_DIR), name="sessions")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class JamOptions(BaseModel):
    genre: str = "synthwave"
    mood: str = "energetic"
    bpm: int | None = Field(default=None, ge=30, le=300)
    theme: str = ""
    vocals: bool = True
    tracks: int = Field(default=config.DEFAULT_TRACKS, ge=1, le=config.MAX_TRACKS)
    duration_sec: float = Field(default=config.DEFAULT_DURATION, ge=10, le=config.MAX_DURATION)
    language: str = "en"
    dj_persona: str = "neon_nina"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/jam")
def jam(opts: JamOptions) -> dict:
    options = opts.model_dump()
    if options["dj_persona"] not in djs.PERSONAS:
        options["dj_persona"] = "neon_nina"
    sid = jukebox.start(options)
    return {"id": sid}


@app.get("/api/session/{sid}")
def session_status(sid: str) -> dict:
    s = jukebox.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return {k: s[k] for k in ("id", "state", "error", "progress", "manifest", "options")}


@app.get("/api/presets")
def presets() -> dict:
    return {
        "genres": config.GENRES,
        "moods": config.MOODS,
        "personas": [{"id": k, **v} for k, v in djs.PERSONAS.items()],
        "max_tracks": config.MAX_TRACKS,
        "max_duration": config.MAX_DURATION,
    }


@app.get("/api/health")
def health() -> dict:
    """Reachability probe for each of the four class services."""
    probes = [
        ("Qwen · text", f"{config.CHAT_BASE_URL}/models", config.CHAT_MODEL),
        ("FLUX · art", f"{config.ART_BASE_URL}/models", config.ART_MODEL),
        ("ACE-Step · music", f"{config.MUSIC_BASE_URL}/v1/model_inventory", config.MUSIC_MODEL),
        ("Chatterbox · DJ", f"{config.TTS_BASE_URL}/models", config.TTS_MODEL),
    ]
    checks = []
    for name, url, model in probes:
        entry = {"name": name, "model": model, "ok": False}
        try:
            r = SESSION.get(url, timeout=10)
            entry["ok"] = r.status_code == 200
            entry["http"] = r.status_code
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)[:100]
        checks.append(entry)
    return {"all_ok": all(c["ok"] for c in checks), "services": checks}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=config.PORT)
