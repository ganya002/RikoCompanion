#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install pygame-ce pillow requests qwen-tts torch soundfile mlx-whisper >/dev/null
source venv/bin/activate
python3 main.py
