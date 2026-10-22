# Verification report - October 22, 2026

This is an agent-prepared test record for the team to review. It does not claim
that a teammate performed an independent install or listening review.

## Reported problem and changes

The reported problem was generated music without singing. The current repository
already enforces a 60-second minimum for vocal tracks. The music client nevertheless
asked ACE-Step to rewrite Qwen's caption and infer the vocal language. This patch
preserves the supplied vocal arrangement, sends `vocal_language` explicitly, and
rejects empty/tag-only lyrics. This is a plausible mitigation, not a proven root-cause
analysis of the original recording: that recording and its request were not supplied,
and no controlled before/after audio comparison was performed.

Other fixes: Resume no longer resets the queue or accumulates click handlers; Skip
is now available; playback pauses before changing clips; DJ introductions precede
the songs they describe; DJ prompts receive the track's BPM and genre from nested
metadata; incomplete DJ scripts retry up to three times; empty covers cause an
understandable generation error; configuration loads from the repository's `.env`;
optional voice references use the documented Chatterbox `ref_audio` request field.

## Automated checks

**69 Python tests passed** (unit/API regressions, the 19 Playwright browser
tests, and the file-based configuration regression tests) and **five Node
playback regressions passed**, executed on the review machine on October 22,
2026. The Playwright browser suite that an earlier pass recorded as unexecuted
(macOS Chromium launch denial) now runs headless and passes. JavaScript syntax
and Git whitespace checks passed. These mock-based tests are separate from the
live service checks below.

## File-based configuration regression

The README's copy-and-edit `.env` path is explicitly tested. In a temporary copy of
`app/config.py`, `app/clients.py`, and the real `.env.example`, three fresh-process
tests verify: (1) dummy file credentials and all four endpoint overrides load with
no exported `AIJ_*` variables, even from a different working directory; (2) existing
environment variables override the file; and (3) an unrelated working directory's
`.env` is ignored when the project file is absent. The first two tests also check
the actual requests session's Authorization header. All three pass without class
service calls or real secrets. `python-dotenv` is required in both dependency files;
its import no longer silently fails. The README specifies the file location,
Windows/macOS copy commands, restart requirement and environment precedence.

## Actual results

| Check | Inputs and expected result | Actual result |
|---|---|---|
| Vocal songs and covers | Pop, happy, 60 seconds, vocals enabled, three songs, theme “small moments of courage on the way home”; expect original lyrics, playable music and matching FLUX files | Three MP3s and three PNGs generated using class Qwen/ACE-Step/FLUX; available in the library and bundled in `samples/` |
| Singing evidence | Transcribe each sample without providing the expected lyrics; expect recognizable generated words | Local faster-whisper tiny.en recovered lyric phrases from all three; approximate excerpts below. Human lyric fidelity/listening review remains pending |
| Final vocal jam | Vocal request via smoke test: synthwave, energetic, 110 BPM, 60 seconds, one song, Chill Charlie; expect lyrics, music, cover and complete DJ queue | Live smoke test passed 9/9 checks; session `b63ec8cbb9c7` completed without manual recovery |
| Full instrumental jam | Synthwave, energetic, 110 BPM, 10 seconds, two instrumental songs, Chill Charlie; expect songs, covers, default DJ speech, library entries and ordered manifest | Live smoke test passed 9/9 checks; session `0a774b1a40ca`, playlist intro → chat → song → chat → song → outro |
| Voice-reference jam | Jazz, chill, 10 seconds, one instrumental song, app-generated DJ intro used as MP3 reference; expect Chatterbox-generated clips with no reference file saved | Session `27c24d85d881` reached ready; three generated DJ clips and song/cover returned. This verifies the request path, not perceived voice similarity |
| Cover failure | Mock FLUX returning empty bytes; expect visible generation failure, no success claim or library addition | Passed regression test |
| Invalid voice upload | WAV filename with non-audio content; expect HTTP 422, no background build | Passed API regression test |
| Malformed DJ output | Live three-song build returned wrong introduction count; expect rejection and recovery | Initial sample build stopped explicitly after saving songs; a subsequent valid script generated five DJ clips without regenerating music. Bounded script retries added and tested; the separate two-song live jam then completed normally |
| Playback | Browser plays a generated library MP3, shows artwork and original lyrics, and pauses/resumes | Checked through the in-app browser; audio loaded with HTTP 206, playback progress advanced, lyric panel showed the generated text, Pause changed to Resume |
| Queue regression | Retry autoplay without resetting the selected clip; skip pauses first and stops at queue end | Node regression tests pass |
| Generation-progress accessibility (regression found in review) | Three Playwright tests expected a `role=progressbar` element with `aria-valuenow` 0 → 50 → 100 while building; the retro redesign had removed it, so all three timed out (30s each) | Added `#gen-progress` (role=progressbar) to the player and wired `setProgress()` to update it; the three tests passed and the full suite went from 63/66 to 66/66 |
| Fresh live vocal generation (this review) | Pop, happy, 60 seconds, vocals on, one song, theme "morning coffee run"; expect original lyrics, playable 60s MP3, matching FLUX cover, library entry | Session `16546f8b6c98` reached `ready`; 60.0 s MP3 (48 kHz) + PNG cover generated via class services and added to the library |

Automated transcription excerpts (imperfect transcription, not a claim of exact singing):

- **Pocket Light:** “let the shadow go … The key fits tight in the rusty lock … Right at the top”
- **Did You Look Up?:** “Shoulders back, chin high / Catch the sun before it dies … Did you look up tonight?”
- **I held my breath for one more step:** “I held my breath … To the front door … When the world feels new … Never alone”

The local transcription model was used solely as a verification tool. It is not
included in the app, runtime dependencies, or archive. All app generation uses
class services. No user recording was used for the voice-reference test.

## Design judgment

Preserving a complete Qwen vocal arrangement avoids a second language model
rewriting the intended singer/lyrics instructions. Explicit language and actual-word
validation make the request inspectable. The new 60-second samples all produced
recognizable lyric phrases under automated transcription, supporting this choice
without proving it fixes every generation. Audio remains probabilistic: transcripts
contain word substitutions and repeated lines. The team should listen to all three
samples before claiming exact lyric fidelity.

One real failure was the DJ returning the wrong number of introductions. Checking
script structure caught it before a broken queue was marked ready. A bounded retry
balances recovery against repeated service requests. A persistent failure still
returns an error; generated songs saved before DJ failure remain in the library.

## Samples and deployment

`samples/manifest.json` records titles, original Qwen lyrics, FLUX prompts, seeds,
class-service provenance and generation options. Three MP3s and three PNGs are
included. First launch installs these into the local library. Runtime sessions,
user library copies, `.env`, references and local validation tools are excluded.

Clean-archive check: the ZIP was extracted into a new directory, production
dependencies installed in a fresh Python 3.12 environment from `requirements-lock.txt`,
and the app started without credentials. All three sample audio/cover URLs returned
HTTP 200, saved lyrics were present, repeated startup kept exactly three songs, and
a ten-second vocal request returned HTTP 422. This agent-run check does not replace
the required teammate check.

See README for setup and manual exercises. The following final checks must be
completed by the team (each is a task for a person, not an automated claim):
listen to the samples and a fresh vocal song, check perceived custom-voice
similarity, test automatic DJ/music playback and skip over a complete set, and
have a teammate run the GitHub-downloaded ZIP from scratch. The Playwright
browser suite is now executed and green on the review machine; a teammate
running it on a second machine would strengthen the record.

## Publication and teamwork

The local archive is a review build. It is not a ZIP downloaded from GitHub.
The team must review the changes, use its GitHub issue/PR workflow, publish the
reviewed commit, and download that exact version from GitHub. No teammate
contribution/review evidence or Canvas submission is claimed by this report.
