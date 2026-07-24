#!/usr/bin/env bash
# Starts diagram_tool (Memory Machine // Diagram Tool) -- the standalone
# 2D diagram-authoring + AI Remix app, decoupled from the old Digital
# Palimpsest app (root index.html + static/main.js, launched via
# `npm run dev`) and from Pershing Metabolizer itself (frontend/ + app.py
# on :8000). See diagram_tool/app.py's module docstring for how the three
# relate.
#
# 2026-07-17: repointed from a plain `http.server` serving the now-
# superseded PershingMetabolizer_Prototype/index.html to this. Needs
# fastapi/uvicorn/pydantic (see requirements.txt), unlike the old
# http.server target, so this mainly relies on the venv rather than any
# stdlib-only Python on PATH.
#
# URL: http://127.0.0.1:8006

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
VENV_PY_WIN="$ROOT/.venv/Scripts/python.exe"  # Git Bash on Windows

cd "$ROOT"

if [ -x "$VENV_PY" ]; then
    PY="$VENV_PY"
elif [ -x "$VENV_PY_WIN" ]; then
    PY="$VENV_PY_WIN"
elif command -v python3 &>/dev/null; then
    echo "No venv found -- using system python3. If this fails with" \
         "'No module named fastapi', run: pip install -r requirements.txt"
    PY="python3"
elif command -v python &>/dev/null; then
    echo "No venv found -- using system python. If this fails with" \
         "'No module named fastapi', run: pip install -r requirements.txt"
    PY="python"
else
    echo "ERROR: No Python found. Install Python 3.11+, then run:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

echo "Using Python: $PY"
"$PY" diagram_tool/app.py &
SERVER_PID=$!

sleep 2
URL="http://127.0.0.1:8006"
if command -v open &>/dev/null; then
    open "$URL"          # macOS
elif command -v xdg-open &>/dev/null; then
    xdg-open "$URL"       # Linux
elif command -v start &>/dev/null; then
    start "$URL"           # Git Bash/WSL, sometimes
else
    echo "Open $URL in your browser"
fi

wait "$SERVER_PID"
