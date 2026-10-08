#!/usr/bin/env bash
# AI Jukebox launcher (macOS / Linux / git-bash). Windows users: start.bat
set -e
cd "$(dirname "$0")"
echo "[AI Jukebox] setting up..."
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q -r requirements.txt
PORT="${AIJ_PORT:-8000}"
echo "[AI Jukebox] starting on http://127.0.0.1:${PORT}  (set AIJ_PORT to override)"
echo "[AI Jukebox] remember: copy .env.example to .env and fill in AIJ_API_KEY"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
