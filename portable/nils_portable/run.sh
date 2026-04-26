#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

cd "$APP_DIR"

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running installer..."
    "$SCRIPT_DIR/scripts/install.sh"
fi

source venv/bin/activate

export PYTHONPATH="$APP_DIR:$PYTHONPATH"

python3 main.py