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
5. The browser plays the whole set back-to-back: intro → DJ chat → song → DJ chat → song → … → outro.

Sessions are generated in a background thread; the page polls progress and plays when ready.
Artifacts live in `sessions/<id>/` (gitignored) alongside a `manifest.json` playlist.
The player UI supports **light and dark mode** (topbar toggle; remembers your choice;
defaults to the system preference).

## Deploy from the ZIP (grader checklist)

The submission is self-contained: no credentials, no generated media, no
third-party content — everything the app needs comes from the class endpoints.

1. **Unzip** the submission. (No `.env`, no `sessions/` — by design.)
2. **Create the environment** (once):
   - macOS/Linux: Python 3.11+ (`python3.11 -m venv .venv`)
   - Windows: Python 3.11+ (`py -3.11 -m venv .venv`)
3. **Install dependencies**:
   - Windows: `.venv\Scripts\python -m pip install -r requirements.txt`
   - macOS/Linux: `.venv/bin/python -m pip install -r requirements.txt`
4. **Create the local configuration file**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and replace the dummy `AIJ_API_KEY` value with the class key. The
   application loads this root-level `.env` automatically at startup; do not run
   `source .env`.
5. **Configuration values**:
   - Required: `AIJ_API_KEY` — obtain it from the MBAX 6418 class service instructions.
   - Optional URL overrides: `AIJ_CHAT_BASE_URL`, `AIJ_ART_BASE_URL`,
     `AIJ_MUSIC_BASE_URL`, and `AIJ_TTS_BASE_URL`. Each must begin with `http://`
     or `https://`.
   - Optional model/voice overrides: `AIJ_CHAT_MODEL`, `AIJ_ART_MODEL`,
     `AIJ_MUSIC_MODEL`, `AIJ_MUSIC_LM_MODEL`, and `AIJ_TTS_MODEL`/`AIJ_TTS_VOICE`.
   - Optional `AIJ_PORT` defaults to `8000` and must be between 1 and 65535.
   - Values exported in the shell override values from `.env`.
   - `.env.example` contains placeholders only. Never commit `.env` or put real
     credentials in code, logs, screenshots, tests, or documentation.
6. **Run**:
   - Windows: double-click `start.bat`
   - macOS/Linux: `./start.sh`
   - or directly: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
   - Port override: set `AIJ_PORT` (e.g. `AIJ_PORT=8080`).
7. **Open** http://127.0.0.1:8000 — the four header lights should be green.
8. **Test the three core features** — either from the UI (pick a vibe, hit
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
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env and replace the dummy AIJ_API_KEY value.
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
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
  static/     retro cabinet player UI (index.html, retro.css, app.js)
    fonts/    locally hosted Barlow + Fraunces fonts and OFL licenses
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

## Retro cabinet interface

The interface draws on vintage jukebox materials: walnut grain, brass trim,
cream record labels, and coral/amber/turquoise fluorescent tubing. Fraunces is
used for display headings and Barlow for readable controls. Fonts are bundled
locally under their SIL Open Font Licenses; no font CDN is needed at runtime.
The Daylight / After hours switch persists the light/dark preference.

The desktop layout separates creation, playback, and the saved collection.
Tablet and mobile layouts reflow without horizontal scrolling. Keyboard focus,
a skip link, named playback buttons, live status announcements, accessible
progress values, and reduced-motion support are included.

Previous / Pause–Resume / Next controls step through individual playlist entries,
including DJ segments as well as songs, without wrapping at the set boundaries.
The seek bar has a visible circular playhead during loaded audio playback and
supports clicking and keyboard arrows/Home/End. Generation progress does not
show an audio playhead.

### Short vocal songs

Vocal songs now have a visible 60-second minimum in both the UI and API;
instrumental clips still allow 10 seconds. Switching vocals on raises a shorter
slider selection to 60 seconds before submission, with an explanation beside
the control. Direct API requests for shorter vocal songs receive a validation
error rather than silently changing their duration.

At 60 seconds, songs are composed as compact, hook-first performances with a
conservative budget of 1.2 sung words per second. Captions request singing from
the first beat without an instrumental intro, solo or long outro. Before
rendering, the app takes a contiguous excerpt beginning at the first chorus/hook
and removes instrumental sections, preserving the subsequent verse/chorus order
and section labels rather than sorting all choruses ahead of verses. Longer songs retain
their full arrangement. Real-audio checks found that prompt changes alone did
not reliably produce recognizable lyrics in 10–30-second generations, whereas
both tested 60-second generations contained singing. Music generation remains
probabilistic; the minimum and arrangement controls are safeguards, not a
guarantee of exact vocal timing or lyric fidelity. Existing audio is unchanged.

The lyric display uses the music service's returned lyric sheet when available,
falling back to the submitted sheet. The original submitted text is retained as
`written_lyrics`, alongside `lyrics_source`, in new session/library entries.
These are lyric sheets, not audio transcriptions or timestamped karaoke lyrics:
the generator can still repeat, omit or alter words. Existing recordings and
their older saved lyric sheets are not rewritten automatically.

### Title and artist variety

Naming forms rotate independently across genres: titles may be a single word,
a question, a conversational fragment, a concrete detail, or a plainspoken
sentence. Fictional artist identities vary between solo performers, mononyms,
duos, and bands instead of always using the same adjective-noun pattern.

The composer sees recent titles/artists and frequently reused vocabulary from
the whole collection, not only the chosen genre. A deterministic check rejects
exact/near duplicates, superficial punctuation/plural/numbered variants, and
overworked name words. Artist identities also avoid previously used distinctive
name words/surnames, not just identical full names. Listener-requested subject
words can still appear in titles. Accepted names are reserved before audio
generation so pending tracks in a set and simultaneous requests also inform
later drafts. Saved collection names are reloaded after restarts. Form rotation
is process-local, as are reservations for the latest 200 accepted specs. An
accepted name from a subsequently failed session remains reserved until eviction
or restart.

Conflicting names trigger up to three complete composition drafts, preserving
the connection between title, lyric hook, and cover scene. There is no post-hoc
number suffix or random rename of finished audio. Persistent conflicts produce
an explicit error instead of silently accepting a duplicate. Existing songs
and artist names are never renamed by this change. These are lexical checks,
not a guarantee of semantic uniqueness or a worldwide artist-name search.

### Cover-art variety

Every new song receives a varied visual brief before the songwriter creates
its cover prompt: palette, medium, narrative approach, and a matched composition
and richness treatment. Compositions rotate between cinematic worlds, surreal
environments, intricate illustrations, environmental portraits, still-life
tableaux, landscapes, action scenes, photomontage, and bold graphic designs.
Most develop layered scenes, lighting, textures and secondary story details;
the occasional more restrained graphic treatment provides contrast. Covers are
not all reduced to isolated objects or flat icons on empty backgrounds.

Palette, medium, composition and approach use shuffled pools per genre, shared
across sets and single-song requests. Richness stays coupled to its composition
so their instructions agree. Choices are exhausted before reuse, and reshuffling avoids
immediate repeats. The pools are not tied to genre stereotypes: synthwave can
receive a linocut, monochrome photograph, textile illustration, or oil painting
instead of always getting a pink/blue neon cityscape.

The songwriter grounds the scene in the song's theme/story, and the image
renderer also receives the assigned visual brief. The brief and cover prompt
are saved with newly generated session/library tracks. Existing covers are not
changed. Shuffle history is process-local; restarting begins a fresh random
order. Visual variety is guided, not a guarantee that every AI image is unique.

### Removing collection tracks

Use a song's **Remove** action and confirm its title. Removal deletes the saved
collection entry and that entry's copied audio/cover files, but preserves the
original generated DJ-session files. Cancel leaves the song untouched. Removing
the currently selected library song stops that playback; other songs and session
playlists are not deleted.

### Regression tests

With the app running on port 8003 (or set `AIJ_TEST_URL` to its URL):

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m unittest discover -s tests -v
```

Art-direction unit tests check variation, shuffle boundaries, concurrency,
and propagation into composer, renderer, and saved metadata. Collection-removal
tests use isolated temporary directories, never the real collection.

The browser tests use explicitly intercepted API fixtures for deterministic
UI-state checks and a silent WAV for real browser pause/resume testing; they
do not call the AI services. Use `scripts/smoke_test.py --base URL` separately
for real end-to-end music, cover art, and DJ generation.

## Credentials & configuration safeguards

- **Credentials are server-side only.** Copy `.env.example` to `.env`, replace the
  dummy `AIJ_API_KEY`, and restart the app. The root-level `.env` is loaded
  automatically by `app/config.py`; manual `source .env` is not required.
- **Environment precedence is explicit.** If the same variable is exported in the
  shell, that value overrides `.env`.
- **Configuration validation is safe.** Startup reports the variable name and the
  required format for missing keys, malformed URLs, or invalid ports, but never
  prints the supplied key, password, or complete secret value.
- **Keep local credentials private.** `.env` is gitignored and `.env.example`
  contains placeholders only. Never put real credentials in code, logs, screenshots,
  tests, documentation, or browser scripts.
- **Diagnosis:** check that `.env` is at the repository root, confirm its key names
  match `.env.example`, restart the server, and inspect only the variable names and
  non-secret validation message. Do not paste the file or key into an issue/chat.
- **No user uploads or voice-reference recordings** are accepted or stored.
  The DJ voice is Chatterbox's bundled voice — no reference-audio cloning.
  All generated output lives in `sessions/` (gitignored) and is never committed.
- **No third-party music, lyrics, cover art, or voice samples are bundled.**
  Every song, cover, and DJ clip is generated at runtime by the class services.

## Git workflow

Work happens on personal branches (e.g. `LN-Branch`); `main` is kept stable and only
changes via an agreed merge/PR. Nothing here is pushed anywhere without approval.
