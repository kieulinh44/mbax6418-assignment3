"""Automated verification of the AI Jukebox's THREE core features.

Runs against a LIVE server (start it first with start.bat / start.sh) and
exercises the same HTTP API the browser uses:

  1. Customizable song generation ......... ACE-Step  (port 9007)
  2. Matching cover art ................... FLUX      (port 9006)
  3. AI-spoken DJ commentary & playback ... Chatterbox (port 9008)
     (plus Qwen composition on 9001)

Usage:
    .venv/Scripts/python scripts/smoke_test.py [--base http://127.0.0.1:8000]
                                              [--tracks 1] [--duration 15]

Exit code 0 = all features PASS. The run takes roughly 1-3 minutes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

RESULTS: list[tuple[str, bool, str]] = []


def check(feature: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((feature, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {feature}" + (f"  ({detail})" if detail else ""))


def http_get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode()


def http_post(url: str, payload: dict, timeout: int = 30) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, f"http {e.code}"
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Jukebox three-feature smoke test")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--tracks", type=int, default=1)
    ap.add_argument("--duration", type=int, default=15)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"== AI Jukebox smoke test  (server: {base}) ==")

    # --- app shell ----------------------------------------------------------
    code, body = http_get(f"{base}/")
    check("App serves the player UI", code == 200 and b"AI" in body and b"JUKEBOX" in body,
          f"GET / -> {code}")

    # --- class services reachable --------------------------------------------
    code, data = http_get(f"{base}/api/health")
    ok = False
    if code == 200:
        try:
            ok = json.loads(data).get("all_ok") is True
        except Exception:  # noqa: BLE001
            pass
    check("All four class services reachable", ok, "GET /api/health")

    # --- create a jam ----------------------------------------------------------
    options = {
        "genre": "synthwave",
        "mood": "energetic",
        "bpm": 110,
        "theme": "automated smoke test",
        "vocals": False,
        "tracks": args.tracks,
        "duration_sec": max(10, args.duration),
        "language": "en",
        "dj_persona": "chill_charlie",
    }
    code, data = http_post(f"{base}/api/jam", options)
    try:
        sid = data["id"]
    except (TypeError, KeyError):
        check("Jam session starts", False, f"POST /api/jam -> {code} {data}")
        return _summary()
    check("Jam session starts", True, f"session {sid}")

    # --- poll until ready -----------------------------------------------------
    state, error, manifest = "queued", "", None
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(10)
        code, data = http_get(f"{base}/api/session/{sid}")
        if code != 200:
            continue
        try:
            d = json.loads(data)
        except Exception:  # noqa: BLE001
            continue
        state = d.get("state", "")
        error = d.get("error") or ""
        if state == "ready":
            manifest = d.get("manifest")
            break
        if state == "error":
            break
    check("Jam completes successfully", state == "ready",
          f"state={state}" + (f" error={error}" if error else ""))

    if manifest is None:
        return _summary()

    playlist = manifest["playlist"]
    songs = [i for i in playlist if i["kind"] == "song"]
    chats = [i for i in playlist if i["kind"] == "chat"]
    intros = [i for i in playlist if i["kind"] == "intro"]
    outros = [i for i in playlist if i["kind"] == "outro"]

    # --- feature 1: songs ------------------------------------------------------
    song_files_ok = True
    for s in songs:
        code, body = http_get(f"{base}{s['audio']}")
        if code != 200 or len(body) < 10_000 or not body.startswith(b"ID3"):
            song_files_ok = False
    check(f"FEATURE 1 - customizable songs (ACE-Step): {len(songs)} generated",
          len(songs) >= args.tracks and song_files_ok,
          ", ".join(f"{s['title']} by {s['artist']}" for s in songs) or "none")

    # --- feature 2: cover art ----------------------------------------------------
    art_ok = True
    for s in songs:
        if not s.get("art"):
            art_ok = False
            continue
        code, body = http_get(f"{base}{s['art']}")
        if code != 200 or len(body) < 10_000 or not body.startswith(b"\x89PNG"):
            art_ok = False
    check(f"FEATURE 2 - matching cover art (FLUX): {len(songs)} images",
          len(songs) >= args.tracks and art_ok)

    # --- feature 3: DJ commentary -------------------------------------------------
    dj_items = intros + chats + outros
    dj_ok = True
    for c in dj_items:
        code, body = http_get(f"{base}{c['audio']}")
        if code != 200 or len(body) < 5_000 or not body.startswith(b"ID3"):
            dj_ok = False
    check(f"FEATURE 3 - AI DJ commentary (Chatterbox): {len(dj_items)} clips "
          f"({len(intros)} intro, {len(chats)} interludes, {len(outros)} outro)",
          dj_ok and intros and outros and chats)

    # --- library (rubric: "add it to the library") --------------------------------
    code, data = http_get(f"{base}/api/library")
    lib_tracks: list = []
    if code == 200:
        try:
            lib_tracks = json.loads(data).get("tracks", [])
        except Exception:  # noqa: BLE001
            pass
    lib_ok = len(lib_tracks) >= args.tracks
    if lib_ok:
        newest = lib_tracks[0]
        code, body = http_get(f"{base}{newest['audio_url']}")
        lib_ok = code == 200 and len(body) > 10_000 and body.startswith(b"ID3")
    check(f"Generated songs added to the persistent library ({len(lib_tracks)} "
          f"of {args.tracks}+ present, newest playable)",
          lib_ok, ", ".join(f"{t['title']} by {t['artist']}" for t in lib_tracks[:2]) or "empty")

    # --- playback order -------------------------------------------------------------
    order = [i["kind"] for i in playlist]
    expected = ["intro"] + ["song", "chat"] * len(songs)
    expected = expected[: len(songs) * 2 + 1] + ["outro"]
    check("Playlist order: intro -> song -> DJ chat -> ... -> outro",
          order == expected, " -> ".join(order))

    return _summary()


def _summary() -> int:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n== {passed}/{len(RESULTS)} checks passed ==")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
