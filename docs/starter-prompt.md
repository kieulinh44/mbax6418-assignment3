# Retained assignment starter prompt

The supplied starter prompt is retained below. The additions afterward describe
implementation safeguards; the team should review and amend them in its own words.

```
# Overarching Task: Build an AI Jukebox
Build an app that (1) generates customizable songs, (2) generates
matching cover art, and (3) plays a song collection with AI-generated
spoken DJ commentary between tracks.
# Required Class Services
- Qwen3.6-35B-A3B on port 9001 for text generation.
- FLUX.2 klein 4B on port 9006 for cover art.
- ACE-Step 1.5 XL Turbo on port 9007 for music.
- Chatterbox Multilingual V3 on port 9008 for DJ speech.
Use the supplied class-endpoints.txt for connection details, or ask our
team if it is unavailable. Follow each service's documented request
format. Use these class services for the required features. You may use
other class endpoints for optional features, but the core app must work
with class services and credentials alone. Do not use paid services for
any app features, including optional features. Do not use port 9000 for
app requests.
# Safeguards
- Keep credentials server-side and out of GitHub, submission archives,
browser code, logs, and documentation. Use placeholders in configuration
examples.
- Never commit user uploads or voice-reference recordings to GitHub or
include them in submission archives.
- Do not bundle third-party music, lyrics, cover art, or voice samples
with the app.
```

## Added build instructions

- Preserve explicit vocal direction and pass original generated lyrics and their
  language to ACE-Step. Reject empty or tag-only vocal lyrics before generation.
- Require at least 60 seconds for vocal songs; short instrumentals remain available.
- Keep one browser audio element for DJ/music sequencing. Resume the current clip
  after an autoplay rejection; expose pause, resume and skip controls.
- Require a nonempty generated FLUX cover and exactly one DJ introduction per song.
  Retry invalid DJ scripts up to three times and expose remaining failures.
- Hold optional voice-reference recordings in memory only during the jam build.
- Include three generated sample audio files and their matching covers. Import
  samples into the local library on first launch without class credentials.
- Separate actual live checks, deterministic tests, transcription evidence, and
  outstanding human listening/deployment checks in the verification report.
