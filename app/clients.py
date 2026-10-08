"""Thin HTTP clients for the four MBAX 6418 class services.

- Qwen3.6-35B (9001): chat completions (text)
- FLUX.2 klein (9006): text-to-image
- ACE-Step 1.5 XL Turbo (9007): text-to-music (custom async job API)
- Chatterbox V3 (9008): text-to-speech

All request formats below were verified directly against the live services.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time

import requests

from . import config

log = logging.getLogger("aijukebox.clients")

SESSION = requests.Session()
if not config.API_KEY:
    log.warning("AIJ_API_KEY is not set — class services will reject requests. "
                "Copy .env.example to .env and fill it in.")
SESSION.headers.update({"Authorization": f"Bearer {config.API_KEY}"})

_TIMEOUT = 180  # generous; image/music generation can be slow


def _post_json(url: str, payload: dict, timeout: int = _TIMEOUT) -> dict:
    r = SESSION.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------
# Qwen (9001) - chat completions
# --------------------------------------------------------------------------

def chat(system: str, user: str, *, max_tokens: int = 2000, temperature: float = 0.7,
         json_mode: bool = False, retries: int = 2) -> str:
    """Single chat completion, retried. The Qwen model spends a LOT of output
    budget on hidden reasoning, so keep ``max_tokens`` generous and grow it on
    every retry; as a last resort, mine the answer out of the reasoning field."""
    payload = {
        "model": config.CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    last_err = "empty response"
    for attempt in range(retries + 1):
        try:
            data = _post_json(f"{config.CHAT_BASE_URL}/chat/completions", payload, timeout=240)
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            if content:
                return content
            reason = (msg.get("reasoning_content") or "") or (msg.get("reasoning") or "")
            finish = data["choices"][0].get("finish_reason")
            if reason.strip():
                if json_mode:
                    mined = _last_json(reason)
                    if mined is not None:
                        return mined
                last_err = "answer only in reasoning field (unparseable)"
            if finish == "length":
                last_err = f"truncated: only {payload['max_tokens']} tokens of budget"
            log.warning("chat attempt %d: %s; retrying with +1500 tokens",
                        attempt + 1, last_err)
            payload["max_tokens"] += 1500
        except Exception as exc:  # noqa: BLE001
            last_err = f"{exc}"
            log.warning("chat attempt %d failed: %s", attempt + 1, exc)
    raise RuntimeError(f"Qwen chat failed: {last_err[:300]}")


def chat_json(system: str, user: str, *, max_tokens: int = 2500,
              temperature: float = 0.6, retries: int = 2) -> dict:
    """Chat completion with tolerated JSON-object parsing."""
    text = chat(system, user, max_tokens=max_tokens, temperature=temperature,
                json_mode=True, retries=retries)
    if isinstance(text, dict):  # already mined from reasoning
        return text
    return parse_json(text)


def parse_json(text: str) -> dict:
    """Exact ``json.loads`` first, then the LAST valid JSON document in the text
    (a reasoning field often contains a draft JSON before the final answer)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except Exception:
        pass
    best = _last_json(text)
    if best is not None:
        return best
    raise ValueError("could not parse JSON from model output: " + text[:200])


def _last_json(text: str) -> dict | None:
    """Return the last valid JSON object found in ``text``, or None."""
    dec = json.JSONDecoder()
    best = None
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            break
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                best = obj
            i = end
        except ValueError:
            i += 1
    return best


# --------------------------------------------------------------------------
# FLUX (9006) - text-to-image
# --------------------------------------------------------------------------

def generate_cover_art(prompt: str, size: str = "1024x1024") -> bytes:
    """Text-to-image -> PNG bytes."""
    payload = {"model": config.ART_MODEL, "prompt": prompt, "size": size, "n": 1}
    data = _post_json(f"{config.ART_BASE_URL}/images/generations", payload, timeout=300)
    items = data.get("data") or []
    if not items or not items[0].get("b64_json"):
        raise RuntimeError("FLUX returned no image data")
    return base64.b64decode(items[0]["b64_json"])


# --------------------------------------------------------------------------
# ACE-Step (9007) - text-to-music (official API: release_task -> query_result)
# --------------------------------------------------------------------------

def generate_song(prompt: str, lyrics: str = "", *, bpm: int | None = None,
                  key_scale: str = "", time_signature: str = "",
                  duration: float = 30.0, audio_format: str = "mp3",
                  thinking: bool = True, seed: int | None = None,
                  poll_interval: float = 3.0, max_wait: float = 300.0) -> tuple[bytes, dict]:
    """Submit a text2music job, poll until done, download the audio.

    Returns ``(audio_bytes, meta_dict)``. Raises on failure/timeout.
    """
    payload: dict = {
        "task_type": "text2music",
        "prompt": prompt,
        "lyrics": lyrics,
        "audio_duration": float(duration),
        "audio_format": audio_format,
        "inference_steps": 8,
        "batch_size": 1,
        "thinking": bool(thinking),
        "use_cot_caption": True,
        "use_cot_language": True,
    }
    if bpm:
        payload["bpm"] = int(bpm)
    if key_scale:
        payload["key_scale"] = key_scale
    if time_signature:
        payload["time_signature"] = str(time_signature)
    if seed is not None:
        payload["use_random_seed"] = False
        payload["seed"] = int(seed)

    submit = _post_json(f"{config.MUSIC_BASE_URL}/release_task", payload, timeout=120)
    task_id = submit["data"]["task_id"]

    started = time.time()
    while time.time() - started < max_wait:
        time.sleep(poll_interval)
        q = _post_json(f"{config.MUSIC_BASE_URL}/query_result",
                       {"task_id_list": [task_id]}, timeout=60)
        row = q["data"][0]
        status = int(row.get("status", 0))
        if status == 2:
            raise RuntimeError(f"ACE-Step task failed: {row.get('progress_text', '')}")
        if status == 1:
            items = json.loads(row["result"])
            entry = items[0]
            file_url = entry["file"]
            r = SESSION.get(f"{config.MUSIC_BASE_URL}{file_url}", timeout=180)
            r.raise_for_status()
            meta = {
                "task_id": task_id,
                "prompt": entry.get("prompt", prompt),
                "lyrics": entry.get("lyrics", lyrics),
                "metas": entry.get("metas", {}),
                "dit_model": entry.get("dit_model", ""),
                "lm_model": entry.get("lm_model", ""),
                "seed_value": entry.get("seed_value", ""),
                "gen_time_s": round(time.time() - started, 1),
            }
            return r.content, meta
        # still queued/running
    raise TimeoutError(f"ACE-Step task {task_id} did not finish in {max_wait}s")


# --------------------------------------------------------------------------
# Chatterbox (9008) - text-to-speech
# --------------------------------------------------------------------------

def generate_speech(text: str, *, voice: str | None = None,
                    response_format: str = "mp3", speed: float = 1.0) -> bytes:
    """Text -> mp3 bytes. ``voice`` defaults to the configured bundled voice."""
    payload = {
        "model": config.TTS_MODEL,
        "input": text,
        "voice": voice or config.TTS_VOICE,
        "response_format": response_format,
        "speed": float(speed),
    }
    r = SESSION.post(f"{config.TTS_BASE_URL}/audio/speech", json=payload, timeout=180)
    r.raise_for_status()
    return r.content
