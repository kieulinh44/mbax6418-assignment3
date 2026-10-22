"""AI Jukebox - FastAPI entrypoint.

Run:  .venv/Scripts/python -m uvicorn app.main:app --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator, ValidationError

from . import config, djs, jukebox, library
from .clients import SESSION

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app):
    library.install_samples()
    yield


app = FastAPI(title="AI Jukebox", version="0.3.0", lifespan=lifespan)

app.mount("/sessions", StaticFiles(directory=jukebox.SESSIONS_DIR), name="sessions")
app.mount("/library", StaticFiles(directory=library.LIBRARY_DIR), name="library")
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

    @model_validator(mode='after')
    def validate_vocal_duration(self):
        if self.vocals and self.duration_sec < config.MIN_VOCAL_DURATION:
            raise ValueError(f'Vocal songs need at least {config.MIN_VOCAL_DURATION} seconds '
                             'so singing has time to start. Disable vocals for shorter clips.')
        return self


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


@app.post("/api/jam-with-voice")
async def jam_with_voice(options: str = Form(...), reference: UploadFile = File(...)) -> dict:
    """Reference bytes remain in memory for this generation; never saved or served."""
    try:
        opts = JamOptions.model_validate_json(options)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid jam options")
    try:
        audio = await reference.read(10 * 1024 * 1024 + 1)
    finally:
        await reference.close()
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Voice reference must be at most 10 MB")
    suffix = Path(reference.filename or "").suffix.lower()
    wav = audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"
    mp3 = audio.startswith(b"ID3") or (len(audio) > 1 and audio[0] == 255 and audio[1] & 224 == 224)
    if not ((suffix == ".wav" and wav) or (suffix == ".mp3" and mp3)):
        raise HTTPException(status_code=422, detail="Upload an MP3 or WAV voice reference")
    settings = opts.model_dump()
    if settings["dj_persona"] not in djs.PERSONAS:
        settings["dj_persona"] = "neon_nina"
    return {"id": jukebox.start(settings, reference_audio=audio)}


@app.post("/api/custom-song")
def custom_song(opts: JamOptions) -> dict:
    """Generate ONE song (style/mood/duration/vocals from the request) and add
    it to the library. Skips DJ commentary — a single song is just song + cover."""
    options = opts.model_dump()
    options["tracks"] = 1
    options["custom_single"] = True
    sid = jukebox.start(options)
    return {"id": sid}


@app.get("/api/library")
def library_list() -> dict:
    """All generated songs, newest first (persistent across restarts)."""
    return {"tracks": library.list_tracks()}


@app.delete("/api/library/{track_id}")
def library_remove(track_id: str) -> dict:
    try:
        library.remove(track_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid song ID")
    except KeyError:
        raise HTTPException(status_code=404, detail="Song not found")
    except OSError:
        library.log.exception("Could not remove library song %s", track_id)
        raise HTTPException(status_code=500, detail="Could not remove song. Check local files and try again.")
    return {"removed": track_id}


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
        "min_vocal_duration": config.MIN_VOCAL_DURATION,
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
