#!/usr/bin/env bash
# deploy.sh — Upload oscilloscope tester files to a Raspberry Pi Pico
#
# Usage:
#   ./deploy.sh               # auto-detect port
#   ./deploy.sh /dev/ttyACM1  # specify port
#
# Requires:  mpremote  (install with:  pip install mpremote)

set -e

PORT="${1:-}"

echo "=== Oscilloscope Tester — deploy to Pico ==="

# ── Locate mpremote ────────────────────────────────────────────────────────
if ! command -v mpremote &>/dev/null; then
    echo "ERROR: 'mpremote' not found. Install it with:"
    echo "       pip install mpremote"
    exit 1
fi

# ── Build mpremote connect string ─────────────────────────────────────────
if [[ -n "$PORT" ]]; then
    CONNECT="connect $PORT"
    echo "Using port: $PORT"
else
    CONNECT=""
    echo "Port: auto-detect"
fi

# ── Upload files ───────────────────────────────────────────────────────────
echo ""
echo "Uploading waveforms.py ..."
mpremote $CONNECT cp waveforms.py :waveforms.py

echo "Uploading main.py ..."
mpremote $CONNECT cp main.py :main.py

echo ""
echo "Done! Files on Pico:"
mpremote $CONNECT ls

echo ""
echo "Opening serial terminal (Ctrl-] or Ctrl-X to exit) ..."
echo "The menu will appear. Type a number and press Enter."
echo ""
mpremote $CONNECT
