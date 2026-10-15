# MBAX 6418 — Assignment 3: AI Jukebox

Build an app that (1) generates **customizable songs**, (2) generates **matching cover art**,
and (3) **plays a song collection with AI-generated spoken DJ commentary** between tracks.

Everything runs on the **class AI services — no paid APIs, no local models**.

## Class services (verified working)

| Feature | Service | Endpoint | Request format (verified) |
|---|---|---|---|
| Song composing, lyrics, DJ scripts | Qwen3.6-35B-A3B-AWQ-4bit · port **9001** | `POST /v1/chat/completions` | `{model, messages, max_tokens, chat_template_kwargs: {enable_thinking: false}}` — thinking disabled (verified: ~1s replies, no hidden-reasoning truncation); JSON via `response_format` |
| Cover art | FLUX.2 klein 4B · port **9006** | `POST /v1/images/generations` | `{model, prompt, size, n}` → `data[].b64_json` (PNG) |
| Music | ACE-Step 1.5 XL Turbo · port **9007** | `POST /release_task` → `POST /query_result` → `GET /v1/audio?path=…` | submit `{prompt, lyrics, bpm, key_scale, time_signature, audio_duration, audio_format, thinking, …}`; poll `{task_id_list}` → status `1`; download via returned `file` URL |
| DJ speech | Chatterbox Multilingual V3 · port **9008** | `POST /v1/audio/speech` | `{model, input, voice, response_format, speed}` → mp3 |

API key and endpoints are read from environment / `.env` (`AIJ_API_KEY`, `AIJ_CHAT_BASE_URL`, …)
with defaults pointing at the class services. See `app/config.py`.

## How it works

A "jam" session is one customizable set:

1. **You customize**: genre, mood, tempo, theme/keywords, vocals on/off, number of songs,
   song length, DJ persona.
2. **Qwen** writes each song (lyrics with [Verse]/[Chorus] structure, a rich music caption,
   BPM/key/time signature, cover-art prompt) *and* the DJ's spoken script.
3. **ACE-Step** generates each song's audio; **FLUX** paints the matching cover art.
4. **Chatterbox** speaks the DJ persona's intro, interludes, and outro.
5. The browser plays the whole set back-to-back: intro → song → DJ chat → song → … → outro.

Sessions are generated in a background thread; the page polls progress and plays when ready.
Artifacts live in `sessions/<id>/` (gitignored) alongside a `manifest.json` playlist.
The player UI supports **light and dark mode** (topbar toggle; remembers your choice;
defaults to the system preference).

## Deploy from the ZIP (grader checklist)

The submission is self-contained: no credentials, no generated media, no
third-party content — everything the app needs comes from the class endpoints.

1. **Unzip** the submission. (No `.env`, no `sessions/` — by design.)
2. **Create the environment** (once):
   - Windows: `python -m venv .venv`
   - macOS/Linux: `python3 -m venv .venv`
3. **Install dependencies**:
   - Windows: `.venv\Scripts\python -m pip install -r requirements.txt`
   - macOS/Linux: `.venv/bin/python -m pip install -r requirements.txt`
4. **Credentials**: copy `.env.example` to `.env` and set `AIJ_API_KEY` to the
   key from `class-endpoints.txt` (or export it as an environment variable).
5. **Run**:
   - Windows: double-click `start.bat`
   - macOS/Linux: `./start.sh`
   - or directly: `python -m uvicorn app.main:app --port 8000`
   - Port override: set `AIJ_PORT` (e.g. `AIJ_PORT=8080`).
6. **Open** http://127.0.0.1:8000 — the four header lights should be green.
7. **Test the three core features** — either from the UI (pick a vibe, hit
   "Start the jam": songs + covers + DJ commentary in one set), or automated:

   ```bash
   .venv/Scripts/python scripts/smoke_test.py          # Windows
   .venv/bin/python scripts/smoke_test.py              # macOS/Linux
   ```

   The smoke test creates a real 1–2 song set and prints PASS/FAIL per feature:
   song generation (ACE-Step), cover art (FLUX), DJ commentary (Chatterbox),
   and playlist order. Exit code 0 = all pass.

## Run (developer shorthand)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — status lights in the header show whether all four
class services are reachable, and `scripts/smoke_test.py` automates the
three-feature verification (see "Deploy from the ZIP").

## Layout

```
app/
  main.py     FastAPI routes + service health
  config.py   endpoints / credentials (env-overridable, class defaults)
  clients.py  verified HTTP clients for the 4 class services
  songs.py    Qwen song composer (customization -> production spec)
  art.py      FLUX cover-art generation
  djs.py      DJ script writing (Qwen) + speech (Chatterbox)
  library.py  persistent track library (index + copied artifacts, gitignored)
  jukebox.py  background session builder (playlist manifest)
  static/     player UI (index.html, style.css, app.js)
scripts/
  smoke_test.py   automated three-feature verification (grader-friendly)
start.bat / start.sh   one-command launchers (venv + install + run)
sessions/     generated audio/art/playlists (gitignored)
```

## Feature checklist (rubric mapping)

| Requirement | Where it lives |
|---|---|
| Choose a song's style, mood, duration | controls panel (genre · mood · tempo · theme · song length · vocals) + "Generate one song" button / `POST /api/custom-song` |
| Generate playable audio with ACE-Step | every song is rendered by ACE-Step (9007) — see `app/clients.py:generate_song` |
| Add it to the library | every generated song is auto-added to the persistent library (`app/library.py`, index in `library/tracks.json`); browsable & playable in the Library panel |
| Instrumental + vocal tracks, AI lyrics for vocal | "Vocals" toggle; vocal tracks get full Qwen-written lyrics with section tags, shown in the player (🎤 Lyrics) |

## Credentials & safeguards

- **Credentials are server-side only.** Copy `.env.example` to `.env` and fill in
  `AIJ_API_KEY`; the app reads it from the environment at runtime. `.env` is
  gitignored — never commit it, and never put a real key in code, docs, logs,
  or browser scripts. The UI talks to this server, which holds the key; the
  browser never sees it.
- **No user uploads or voice-reference recordings** are accepted or stored.
  The DJ voice is Chatterbox's bundled voice — no reference-audio cloning.
  All generated output lives in `sessions/` (gitignored) and is never committed.
- **No third-party music, lyrics, cover art, or voice samples are bundled.**
  Every song, cover, and DJ clip is generated at runtime by the class services.

## Git workflow

Work happens on personal branches (e.g. `LN-Branch`); `main` is kept stable and only
changes via an agreed merge/PR. Nothing here is pushed anywhere without approval.
