#!/usr/bin/env bash
# AI Jukebox launcher (macOS / Linux / git-bash). Windows users: start.bat
set -e
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  echo "Setup failed: Python 3.11+ is required (set PYTHON_BIN to its executable)." >&2
  exit 1
}
echo "[AI Jukebox] setting up..."
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q -r requirements.txt
PORT="${AIJ_PORT:-8000}"
echo "[AI Jukebox] starting on http://127.0.0.1:${PORT}  (set AIJ_PORT to override)"
echo "[AI Jukebox] configuration: copy .env.example to .env; AIJ_API_KEY is required"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
