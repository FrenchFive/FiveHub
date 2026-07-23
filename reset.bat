@echo off
rem FIVE HUB factory reset (Windows) — uninstall + fresh install in one go.
rem Your projects are kept. Close the FiveHub app and Houdini first.
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

%PY% uninstall.py --reinstall %*
echo.
pause
endlocal
