#!/usr/bin/env bash
# Start the Pershing Metabolizer dev server from the repo root.
# Works on Mac/Linux/WSL/Git Bash -- no hardcoded paths.
#
# URL: http://localhost:8000/PershingMetabolizer_Prototype/index.html

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"

cd "$ROOT"

if [ -x "$VENV_PY" ]; then
    echo "Using venv Python: $VENV_PY"
    "$VENV_PY" -m http.server 8000
elif command -v python3 &>/dev/null; then
    echo "Using system python3"
    python3 -m http.server 8000
elif command -v python &>/dev/null; then
    echo "Using system python"
    python -m http.server 8000
else
    echo "ERROR: No Python found."
    exit 1
fi
