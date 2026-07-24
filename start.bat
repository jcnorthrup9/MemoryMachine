@echo off
REM Starts diagram_tool (Memory Machine // Diagram Tool) -- the standalone
REM 2D diagram-authoring + AI Remix app, decoupled from the old Digital
REM Palimpsest app (root index.html plus static main.js, launched via
REM npm run dev) and from Pershing Metabolizer itself (frontend plus
REM app.py on port 8000). See diagram_tool/app.py's module docstring for
REM how the three relate.
REM
REM 2026-07-17: repointed from a plain http.server serving the now-
REM superseded PershingMetabolizer_Prototype/index.html to this, since that
REM prototype is dead weight and this is what "open the app" should mean
REM now. Needs fastapi/uvicorn/pydantic (see requirements.txt), unlike the
REM old http.server target, so unlike before this script mainly relies on
REM the venv rather than any stdlib-only Python on PATH.
REM
REM URL: http://127.0.0.1:8006

set ROOT=%~dp0

REM cd to repo root first -- avoids trailing-backslash quoting issues
cd /d "%ROOT%"

set VENV_PY=%ROOT%.venv\Scripts\python.exe
if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 (
        echo Using venv Python: %VENV_PY%
        start "Memory Machine - Diagram Tool" "%VENV_PY%" diagram_tool\app.py
        REM ping as a portable delay -- unlike "timeout /t", it never
        REM touches stdin, so it doesn't break when this script runs with
        REM redirected/piped input (automation, remote invocation, etc).
        ping -n 3 127.0.0.1 >nul
        start "" http://127.0.0.1:8006
        goto :done
    )
    echo Venv Python exists but is broken, trying system Python...
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo Using system python -- if this fails with "No module named fastapi",
    echo run: pip install -r requirements.txt   -- or fix the venv instead
    start "Memory Machine - Diagram Tool" python diagram_tool\app.py
    ping -n 3 127.0.0.1 >nul
    start "" http://127.0.0.1:8006
    goto :done
)

echo ERROR: No Python found. Install Python 3.11+, then run:
echo   pip install -r requirements.txt
pause
:done
