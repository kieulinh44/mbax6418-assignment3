"""DJ commentary: Qwen (9001) writes the spoken script, Chatterbox (9008) speaks it."""
from __future__ import annotations

from .clients import chat_json, generate_speech

SYSTEM_PROMPT = """You are the on-air DJ of the AI Jukebox -- a charismatic radio host introducing AI-generated songs.

Write spoken-only script lines that will be read aloud by a text-to-speech voice. Rules:
- Each clip is 1-3 short sentences: catchy, conversational, easy to speak.
- NO markdown, NO brackets or tags, NO emojis, NO stage directions, NO quotation marks around titles -- say titles naturally.
- Spell numbers as words ("one hundred twenty beats per minute", "two thousand twenty six").
- Match the ENERGY AND TONE of the persona given to you.
- intro: welcome the listener and tease the set (2-3 sentences).
- tracks: one clip per track, IN THE SAME ORDER AS GIVEN -- hype the track, mention its title and one concrete hook about its sound or theme, then hand off (2-3 sentences each).
- outro: thank the listener and sign off (1-2 sentences).

Respond with ONE JSON object only:
{"intro": "...", "tracks": ["...", "...", ...], "outro": "..."}"""

PERSONAS = {
    "neon_nina": {
        "label": "Neon Nina — high-energy",
        "tone": "high-energy, punchy, hyped, exclamation-forward, festival announcer",
        "speed": 1.08,
    },
    "chill_charlie": {
        "label": "Chill Charlie — laid-back",
        "tone": "cool, mellow, relaxed, gentle dry humor, late-night radio host",
        "speed": 0.96,
    },
    "professor_vinyl": {
        "label": "Professor Vinyl — witty",
        "tone": "witty, playful intelligence, surprising trivia, warm and clever",
        "speed": 1.0,
    },
}


def script_for(persona_id: str, tracks: list[dict], options: dict | None = None) -> dict:
    """Write {intro, tracks: [...], outro} for the given tracks."""
    persona = PERSONAS.get(persona_id, PERSONAS["neon_nina"])
    options = options or {}
    lines = ["Track list for the set:"]
    for i, t in enumerate(tracks, 1):
        lines.append(
            f"{i}. Title \"{t['title']}\" by {t['artist']} -- {t.get('genres', '')} "
            f"vibe, {t.get('bpm', '?')} BPM, {(t.get('blurb') or t.get('caption') or '')[:140]}"
        )
    user = (
        f"DJ persona: {persona['tone']}.\n"
        f"Set theme: {options.get('theme') or options.get('genre', 'a night of AI music')}.\n"
        + "\n".join(lines)
        + "\nReturn the JSON script."
    )
    return chat_json(SYSTEM_PROMPT, user, max_tokens=4000, temperature=0.85, retries=2)


def render_script(script: dict, persona_id: str) -> dict:
    """Speak every clip with Chatterbox. Returns {intro, tracks: [bytes], outro}."""
    persona = PERSONAS.get(persona_id, PERSONAS["neon_nina"])
    speed = persona["speed"]
    return {
        "intro": generate_speech(script["intro"], speed=speed),
        "tracks": [generate_speech(clip, speed=speed) for clip in script["tracks"]],
        "outro": generate_speech(script["outro"], speed=speed),
    }
