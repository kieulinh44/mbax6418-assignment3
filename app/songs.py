"""Song composition.

Turns a listener's customization (genre / mood / tempo / theme / vocals) into
a complete music-production spec: a rich caption for ACE-Step, full lyrics
with section tags, and musical metadata (BPM, key, time signature). Written
by Qwen (9001) and normalized here.
"""
from __future__ import annotations

import json

from .clients import chat_json
from . import art, naming

SYSTEM_PROMPT = """You are the songwriting brain of an AI jukebox. You turn a listener's customization into a complete music-production order for a text-to-music model (ACE-Step) and write the lyrics.

Songwriting craft (apply it):
- Structure: [Intro] [Verse 1] [Chorus] [Verse 2] [Chorus] [Bridge] [Final Chorus] [Outro] with a strong HOOK (a memorable title phrase) landing in the chorus.
- Show, don't tell: concrete images over emotion-labels. Keep the meter singable; line-to-line syllable counts should match so it can be sung.
- Mix perfect and slant rhymes. Avoid cliches on autopilot.
- Emotional arc: verses lower and sparser, chorus bigger and hooky, bridge a shift, final chorus the peak.

ACE-Step caption craft: describe genre + mood + era + instruments + vocal style + production + a dynamic arc (sparse start, build, peak in the chorus). Describe the journey, not just a genre label, in 2-4 sentences.

Rules:
- Respond with ONE valid JSON object only. No markdown fences, no extra text.
- If vocals are disabled, set "lyrics" to "" and "instrumental" to true.
- Title: follow the assigned title form; 1-8 words and at most 60 characters. Draw from a specific story detail or hook, rather than automatically repeating the theme verbatim or using an adjective plus genre-coded noun.
- Artist: follow the assigned artist form; invent a fictional identity, never name a real artist. It may be a solo name, mononym, duo or band, not always an adjective-noun band name. At most 60 characters. Do not recycle the song title as the artist identity.
- Naming: use the ASSIGNED NAMING BRIEF. Recent names are across ALL genres, including songs composed but not yet saved. Avoid those names, near-spellings, numbered variants and overused vocabulary. Artist identities must also avoid the listed artist_words_to_avoid: do not reuse a surname or signature band word with a different prefix. A subject explicitly requested by the listener may still appear in a title if essential, but artist names should be independent. Genre aesthetics and art materials are NOT a naming word bank. Keep the final title and its sung hook consistent.
- cover_prompt: a vivid finished album-art scene in 3-5 sentences, with NO text, letters or typography. Follow the ASSIGNED VISUAL BRIEF for palette, medium, and the matched composition/richness. Describe the focal subject, its specific environment, interacting secondary details, textures and lighting. For layered treatments, develop foreground, middle distance and atmosphere with discoveries at different scales. For the graphic treatment, use a powerful designed background and a few meaningful details rather than a generic icon on blank paper. Invent imagery from this song's story, lyrics or theme. The musical genre must NOT dictate the palette or visual style. Do not default to neon skylines, sunset grids, guitars or other genre shorthand unless the listener specifically requests that subject.

JSON fields:
{
  "title": string,
  "artist": string,
  "caption": string,
  "lyrics": string,
  "instrumental": boolean,
  "vocal_language": string,
  "bpm": int,
  "key_scale": string,
  "time_signature": string,
  "genres": string,
  "cover_prompt": string
}"""


def compose_track(opts: dict, index: int = 0, total: int = 1) -> dict:
    """Compose one song spec from the session options."""
    direction = art.director.choose(opts.get("genre", "synthwave"))
    rejected = []
    for _ in range(3):
        brief = naming.director.brief()
        user = _user_prompt(opts, index, total, direction, brief)
        if rejected:
            user += "\nRETRY: Previous drafts were rejected. Compose a fresh COMPLETE spec " \
                    "with different names, matching lyrics/hook and cover scene. " \
                    "Do not just rename the old draft or add a number.\n" + "\n".join(rejected)
        spec = chat_json(SYSTEM_PROMPT, user, max_tokens=6000, temperature=0.8, retries=2)
        track = normalize(spec, opts)
        reasons = naming.director.reserve(track, theme=opts.get("theme") or "")
        if not reasons:
            track["art_direction"] = direction
            track["naming_direction"] = {key: brief[key] for key in ("title_form", "artist_form")}
            return track
        rejected.append(json.dumps({"title": track["title"], "artist": track["artist"],
                                    "reasons": reasons}, ensure_ascii=False))
    raise RuntimeError("Generated song/artist names kept repeating after three drafts. "
                       "Try a different theme and generate again.")


def _user_prompt(opts: dict, index: int, total: int, direction: dict | None = None,
                 name_brief: dict | None = None) -> str:
    slot = ""
    if total > 1:
        if index == 0:
            slot = "Role in the set: the OPENING track - hook the listener immediately."
        elif index == total - 1:
            slot = "Role in the set: the CLOSER - an anthemic, memorable finish."
        else:
            slot = f"Role in the set: track {index + 1} of {total} - keep the energy flowing, distinct from the others."
    theme = (opts.get("theme") or "").strip()
    visual_brief = ""
    if direction:
        visual_brief = "\nASSIGNED VISUAL BRIEF (for cover art only, not the music):\n" + "\n".join(
            f"- {key}: {value}" for key, value in direction.items())
    naming_brief = ""
    if name_brief:
        naming_brief = "\nASSIGNED NAMING BRIEF:\n" + json.dumps(name_brief, ensure_ascii=False)
    return f"""Customize ONE song:
- genre: {opts.get('genre', 'synthwave')}
- mood: {opts.get('mood', 'energetic')}
- tempo: {opts.get('bpm') or 'auto (sensible for the genre)'} BPM
- theme/keywords: {theme or 'none - invent something vivid'}
- vocals: {'enabled - write real lyrics' if opts.get('vocals', True) else 'disabled - instrumental only'}
- duration: {opts.get('duration_sec', 30)} seconds
- lyrics language: {opts.get('language', 'en')}
{slot}
{visual_brief}
{naming_brief}
Return the JSON production spec for this song."""


def normalize(spec: dict, opts: dict) -> dict:
    """Clamp/repair whatever the model returned so downstream code never breaks."""
    genre = opts.get("genre", "synthwave")
    mood = opts.get("mood", "energetic")
    theme = (opts.get("theme") or "").strip()
    vocals = bool(opts.get("vocals", True))

    title = str(spec.get("title") or "Untitled").strip()[:60] or "Untitled"
    artist = (str(spec.get("artist") or "The AI Jukebox").strip()[:60]
              or "The AI Jukebox")
    caption = str(spec.get("caption") or "").strip()
    if not caption:
        caption = f"A {mood} {genre} track{f' about {theme}' if theme else ''} with a driving arrangement and clear dynamic arc."
    lyrics = str(spec.get("lyrics") or "").strip() if vocals else ""
    instrumental = (not vocals) or bool(spec.get("instrumental"))
    if instrumental:
        lyrics = ""

    try:
        bpm = int(spec.get("bpm") or opts.get("bpm") or 0)
    except (TypeError, ValueError):
        bpm = 0
    if not (30 <= bpm <= 300):
        bpm = int(opts.get("bpm") or 0)
    if not (30 <= bpm <= 300):
        bpm = _default_bpm(genre, mood)

    key_scale = str(spec.get("key_scale") or "").strip()[:20]
    time_signature = str(spec.get("time_signature") or "").strip()[:4]
    if time_signature not in ("2", "3", "4", "6"):
        time_signature = ""
    vocal_language = str(spec.get("vocal_language") or opts.get("language") or "en").strip()[:10] or "en"

    cover_prompt = str(spec.get("cover_prompt") or "").strip()
    if not cover_prompt:
        cover_prompt = (f"A symbolic album-cover scene about {theme or title}, "
                        f"conveying a {mood} emotion, no text, no typography")

    return {
        "title": title,
        "artist": artist,
        "caption": caption,
        "lyrics": lyrics,
        "instrumental": instrumental,
        "vocal_language": vocal_language,
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": time_signature,
        "genres": str(spec.get("genres") or genre).strip()[:80],
        "cover_prompt": cover_prompt,
    }


def _default_bpm(genre: str, mood: str) -> int:
    table = {
        "synthwave": 110, "lo-fi": 78, "hip-hop": 92, "bossanova": 108,
        "jazz": 120, "metal": 150, "reggaeton": 96, "ambient": 70,
        "country": 100, "electronic": 124, "rock": 128, "pop": 118,
    }
    bpm = table.get(genre, 112)
    if mood == "chill":
        bpm = max(60, bpm - 18)
    elif mood == "melancholic":
        bpm = max(60, bpm - 24)
    elif mood == "energetic":
        bpm = min(180, bpm + 14)
    return bpm
