@echo off
:: Start the Pershing Metabolizer dev server from the repo root.
:: Tests each Python candidate before using it (venv shims can exist but be broken).
::
:: URL: http://localhost:8000/PershingMetabolizer_Prototype/index.html

set ROOT=%~dp0

:: cd to repo root first — avoids trailing-backslash quoting issues with --directory
cd /d "%ROOT%"

:: Test a python candidate: if it runs --version cleanly, use it for the server.
set VENV_PY=%ROOT%.venv\Scripts\python.exe
if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if not errorlevel 1 (
        echo Using venv Python: %VENV_PY%
        "%VENV_PY%" -m http.server 8000
        goto :done
    )
    echo Venv Python exists but is broken, trying system Python...
)

python --version >nul 2>&1
if not errorlevel 1 (
    echo Using system python
    python -m http.server 8000
    goto :done
)

python3 --version >nul 2>&1
if not errorlevel 1 (
    echo Using system python3
    python3 -m http.server 8000
    goto :done
)

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    echo Using py 3.12
    py -3.12 -m http.server 8000
    goto :done
)

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    echo Using py 3.11
    py -3.11 -m http.server 8000
    goto :done
)

:: Node.js fallback — npx serve works without any Python at all
where npx >nul 2>&1
if not errorlevel 1 (
    echo No Python found, falling back to npx serve
    cd /d "%ROOT%"
    npx serve . -p 3000
    goto :done
)

echo ERROR: No Python or Node.js found. Install either to run the dev server.
pause
:done
