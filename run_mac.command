#!/usr/bin/env bash
# Double-click this in Finder to run the macro on mac - same idea as run.bat
# on Windows. First run creates a venv and installs dependencies (takes a
# few minutes); later runs start right away.
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python3" ]; then
    echo "First run - setting up. This takes a few minutes."
    echo
    python3 -m venv .venv
    source .venv/bin/activate
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install -r requirements.txt
    echo
    echo "Setup complete."
    echo
else
    source .venv/bin/activate
fi

python3 main.py
