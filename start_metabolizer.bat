@echo off
REM Starts the Pershing Metabolizer app -- FastAPI backend (app.py,
REM logic/pershing_api.py) on :8000 plus the Vite frontend (frontend/) on
REM :5174 (moved off :5173 2026-07-30), which proxies /api and friends to
REM the backend (see frontend/vite.config.js's API_PROXY). Distinct from
REM start.bat, which launches the separate diagram_tool app on :8006 --
REM don't merge the two, they're different apps.
REM
REM URL: http://127.0.0.1:5174

set ROOT=%~dp0

REM cd to repo root first -- avoids trailing-backslash quoting issues
cd /d "%ROOT%"

set VENV_PY=%ROOT%.venv\Scripts\python.exe
if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 (
        echo Using venv Python: %VENV_PY%
        start "Memory Machine - Backend" "%VENV_PY%" app.py
        goto :frontend
    )
    echo Venv Python exists but is broken, trying system Python...
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo Using system python -- if this fails with "No module named fastapi",
    echo run: pip install -r requirements.txt   -- or fix the venv instead
    start "Memory Machine - Backend" python app.py
    goto :frontend
)

echo ERROR: No Python found. Install Python 3.11+, then run:
echo   pip install -r requirements.txt
pause
goto :done

:frontend
start "Memory Machine - Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

REM ping as a portable delay -- unlike "timeout /t", it never touches
REM stdin, so it doesn't break when this script runs with redirected/piped
REM input (automation, remote invocation, etc).
ping -n 3 127.0.0.1 >nul
start "" http://127.0.0.1:5174
goto :done

:done
