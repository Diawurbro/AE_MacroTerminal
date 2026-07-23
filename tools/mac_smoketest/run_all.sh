#!/usr/bin/env bash
# Runs the 3 mac-port smoke tests in order: window discovery, retina scale,
# then the actual input-accept test (which clicks/taps into Roblox).
#
# Override which Python runs these if `python3` on PATH isn't the one with
# pyobjc installed, e.g.:
#   PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 ./run_all.sh
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

echo "Using interpreter: $PYTHON"
echo "=== 1/3: window discovery ==="
"$PYTHON" 2_window_discovery_test.py
echo
read -p "Press Enter to continue to the retina scale test..."

echo "=== 2/3: retina scale ==="
"$PYTHON" 3_retina_scale_test.py
echo
read -p "Switch to Roblox now, then press Enter to run the input-accept test..."

echo "=== 3/3: input accept (watch Roblox) ==="
"$PYTHON" 1_input_accept_test.py
