"""Jukebox session orchestration.

A "jam" session builds, in a background thread:
    DJ intro -> song 1 (+ cover art) -> DJ chat -> song 2 (+ cover art) -> ... -> DJ outro

Artifacts land in ``sessions/<session_id>/`` and are served by the app; the
manifest (ordered playlist) is what the player consumes.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from pathlib import Path

from . import art as art_mod
from . import config
from . import djs as djs_mod
from . import library as library_mod
from . import songs as songs_mod

log = logging.getLogger("aijukebox.jukebox")

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


# --------------------------------------------------------------------------
# Public API used by the FastAPI layer
# --------------------------------------------------------------------------

def start(options: dict, *, reference_audio: bytes | None = None) -> str:
    sid = uuid.uuid4().hex[:12]
    (SESSIONS_DIR / sid).mkdir(parents=True, exist_ok=True)
    total = int(options.get("tracks", config.DEFAULT_TRACKS))
    custom_single = bool(options.get("custom_single"))
    units = total * 2 + (0 if custom_single else 2)  # songs+covers (+DJ if a set)
    with _lock:
        _sessions[sid] = {
            "id": sid,
            "state": "queued",
            "error": None,
            "options": options,
            "progress": {"stage": "queued", "done": 0, "total": units},
            "manifest": None,
        }
    threading.Thread(target=_build, args=(sid, options, total, reference_audio), daemon=True).start()
    return sid


def get(sid: str) -> dict | None:
    with _lock:
        s = _sessions.get(sid)
        return dict(s) if s else None


def _update(sid: str, **fields) -> None:
    with _lock:
        s = _sessions[sid]
        if "progress" in fields:
            s["progress"].update(fields.pop("progress"))
        s.update(fields)


# --------------------------------------------------------------------------
# Background builder
# --------------------------------------------------------------------------

def _build(sid: str, options: dict, total: int, reference_audio: bytes | None = None) -> None:
    sdir = SESSIONS_DIR / sid
    custom_single = bool(options.get("custom_single"))
    steps = 0  # monotonic work counter for progress
    units = total * 2 + (0 if custom_single else 2)  # songs+covers (+DJ if a set)
    try:
        _update(sid, state="working",
                progress={"stage": "composing songs", "done": 0, "total": units})

        # 1) compose song specs -----------------------------------------------
        specs = []
        for i in range(total):
            spec = songs_mod.compose_track(options, index=i, total=total)
            specs.append(spec)

        # 2) generate each song + cover ---------------------------------------
        tracks: list[dict] = []
        for i, spec in enumerate(specs):
            steps += 1
            _update(sid, progress={"stage": f"generating song {i + 1}/{total}", "done": steps})
            audio, meta = _generate_song(spec, options)
            service_lyrics = meta.get('lyrics')
            service_lyrics = service_lyrics.strip() if isinstance(service_lyrics, str) else ''
            written_lyrics = spec['lyrics']
            has_service_lyrics = bool(service_lyrics)
            # Service metadata may contain a revised lyric sheet. Never discard
            # it in favor of the draft, but do not call it an audio transcription.
            lyrics = service_lyrics if has_service_lyrics and written_lyrics else written_lyrics
            (sdir / f"song_{i + 1}.mp3").write_bytes(audio)
            steps += 1
            _update(sid, progress={"stage": f"painting cover {i + 1}/{total}", "done": steps})
            try:
                cover = art_mod.cover_for(spec)
            except Exception as exc:  # noqa: BLE001 - cover is non-fatal
                log.warning("cover failed for %s: %s", spec.get("title"), exc)
                cover = b""
            if cover:
                (sdir / f"cover_{i + 1}.png").write_bytes(cover)
            tracks.append({
                "kind": "song",
                "title": spec["title"],
                "artist": spec["artist"],
                "blurb": spec["caption"][:220],
                "audio": f"/sessions/{sid}/song_{i + 1}.mp3",
                "art": f"/sessions/{sid}/cover_{i + 1}.png" if cover else "",
                "art_direction": spec.get("art_direction", {}),
                "cover_prompt": spec.get("cover_prompt", ""),
                "meta": {
                    "bpm": spec["bpm"],
                    "genres": spec["genres"],
                    "key_scale": spec["key_scale"],
                    "duration": meta.get("metas", {}).get("duration"),
                    "seed": meta.get("seed_value", ""),
                    "gen_time_s": meta.get("gen_time_s"),
                },
                "lyrics": lyrics,
                "written_lyrics": written_lyrics,
                "lyrics_source": 'music_service' if has_service_lyrics and written_lyrics else 'submitted',
            })

        # 3) add every song to the persistent library (rubric requirement) ----
        for i, t in enumerate(tracks):
            art_path = sdir / f"cover_{i + 1}.png"
            library_mod.add(t, sdir / f"song_{i + 1}.mp3",
                            art_path if art_path.exists() else None,
                            session_id=sid, options=options)

        # 4) DJ script + speech (sets only — a single custom song skips DJ)
        persona = options.get("dj_persona", "neon_nina")
        if not custom_single:
            steps += 1
            _update(sid, progress={"stage": "writing DJ script", "done": steps})
            script = djs_mod.script_for(persona, tracks, options)
            steps += 1
            _update(sid, progress={"stage": "recording DJ voice", "done": steps})
            speech = (djs_mod.render_script(script, persona, reference_audio=reference_audio)
                      if reference_audio else djs_mod.render_script(script, persona))
            (sdir / "dj_intro.mp3").write_bytes(speech["intro"])
            for i, clip in enumerate(speech["tracks"]):
                (sdir / f"dj_chat_{i + 1}.mp3").write_bytes(clip)
            (sdir / "dj_outro.mp3").write_bytes(speech["outro"])

        # 5) assemble the playlist manifest ------------------------------------
        if custom_single:
            playlist = list(tracks)  # just the song(s)
        else:
            playlist: list[dict] = [{
                "kind": "intro",
                "title": "Welcome to the AI Jukebox",
                "artist": options.get("dj_persona", "DJ"),
                "audio": f"/sessions/{sid}/dj_intro.mp3",
                "meta": {},
            }]
            for i, t in enumerate(tracks):
                # DJ introduces the upcoming track, then the song plays
                playlist.append({
                    "kind": "chat",
                    "title": "DJ intro",
                    "artist": persona,
                    "audio": f"/sessions/{sid}/dj_chat_{i + 1}.mp3",
                    "meta": {},
                })
                playlist.append(t)
            playlist.append({
                "kind": "outro",
                "title": "Thanks for listening",
                "artist": persona,
                "audio": f"/sessions/{sid}/dj_outro.mp3",
                "meta": {},
            })

        manifest = {
            "id": sid,
            "title": options.get("theme") or f"{options.get('genre', 'AI')} night",
            "options": options,
            "playlist": playlist,
            "tracks": tracks,
        }
        (sdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _update(sid, state="ready", manifest=manifest,
                progress={"stage": "ready", "done": units, "total": units})
        log.info("session %s ready: %d tracks", sid, total)
    except Exception as exc:  # noqa: BLE001 - surface any failure
        log.exception("session %s failed", sid)
        _update(sid, state="error", error=f"{type(exc).__name__}: {exc}")


def _generate_song(spec: dict, options: dict):
    from .clients import generate_song as gen
    duration = float(options.get('duration_sec', config.DEFAULT_DURATION))
    if options.get('vocals', True):
        if duration < config.MIN_VOCAL_DURATION:
            raise ValueError(f'Vocal songs need at least {config.MIN_VOCAL_DURATION} seconds. '
                             'Disable vocals for shorter clips.')
        caption, lyrics = songs_mod.short_vocal_arrangement(spec['caption'], spec['lyrics'], duration)
        if not re.search(r'[^\W\d_]', re.sub(r'\[[^\]]*\]', '', lyrics), re.UNICODE):
            raise ValueError('Vocal song has no singable lyrics. Please generate again.')
        # Persist exactly the lyrics/arrangement submitted to the music service.
        if duration > 60:
            caption = 'Vocal song with a clearly audible lead singer performing the supplied lyrics. ' + caption
        spec['caption'], spec['lyrics'] = caption, lyrics
    else:
        spec['lyrics'] = ''
    return gen(
        spec["caption"],
        spec["lyrics"],
        bpm=spec.get("bpm") or None,
        key_scale=spec.get("key_scale") or "",
        time_signature=spec.get("time_signature") or "",
        duration=duration,
        thinking=True,
        audio_format="mp3",
        vocal_language=spec.get("vocal_language") or options.get("language", "en"),
    )
