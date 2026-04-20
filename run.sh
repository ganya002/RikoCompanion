#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    ./venv/bin/pip install pygame-ce pillow requests
fi
source venv/bin/activate
python3 main.py
