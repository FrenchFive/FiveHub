@echo off
rem FIVE HUB one-shot installer (Windows) — double-click and you're done.
rem Installs: Houdini package, Pillow, Satoshi fonts, splash, app deps.
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 was not found. Install it from https://python.org and run this again.
    pause
    exit /b 1
)

%PY% install.py %*
echo.
pause
endlocal
