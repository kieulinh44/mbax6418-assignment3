# MBAX 6418 — Assignment 3: AI Jukebox

Build an app that (1) generates **customizable songs**, (2) generates **matching cover art**,
and (3) **plays a song collection with AI-generated spoken DJ commentary** between tracks.

## Status

Scaffolding — in progress on `LN-Branch`. Nothing merged to `main` yet.

## Stack (proposed)

- **Backend**: FastAPI + Uvicorn
- **Song generation**: LLM-composed music (lyrics + chord/melody spec) rendered with procedural synthesis (numpy/scipy)
- **Cover art**: text-to-image via pollinations.ai (free, no key)
- **DJ commentary**: edge-tts neural voices (free, no key)
- **Player**: browser-based jukebox UI served by the app

## Layout

```
app/          FastAPI app: API + jukebox orchestration
  main.py     routes + static serving
  llm.py      DeepSeek (class endpoint) chat client
  music.py    procedural song synthesizer
  art.py      cover art generation
  djs.py      DJ commentary TTS
  jukebox.py  session builder (tracks + commentary + art)
  static/     player UI (index.html, app.js, style.css)
sessions/     generated audio/art artifacts (gitignored)
```

## Run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Then open http://localhost:8000
