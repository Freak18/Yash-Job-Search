#!/bin/bash
set -e
cd "$(dirname "$0")"

PORT=8000

if [ ! -d venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Reinstall only when requirements.txt changed
if ! cmp -s requirements.txt venv/.requirements.installed; then
    echo "Installing dependencies..."
    pip install -q -r requirements.txt
    cp requirements.txt venv/.requirements.installed
fi

if [ ! -f .env ]; then
    echo "Warning: .env not found. Create it (see Start.md) or Sheets/Apify/LLM calls will fail."
fi

# Open the browser once the server is up (macOS: open, Linux: xdg-open)
(
    for _ in $(seq 1 30); do
        if curl -s -o /dev/null "http://localhost:$PORT"; then
            (open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1
            exit 0
        fi
        sleep 1
    done
) &

python server.py
