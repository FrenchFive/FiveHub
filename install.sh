#!/usr/bin/env bash
# FIVE HUB one-shot installer (macOS / Linux).
# Installs: Houdini package, Pillow, Satoshi fonts, splash, app deps.
set -u
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "Python 3 was not found. Install it and run this again."
    exit 1
fi

exec "$PY" install.py "$@"
