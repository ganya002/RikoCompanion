# Riko Companion

Riko Companion is a local macOS desktop companion built with `pygame`. It now has a proper desktop UI, offline neural TTS, screen awareness, and explicit local computer controls instead of just basic text replies.

## What Changed

- Fixed the duplicated/overlapping response rendering at the bottom of the window.
- Reworked the layout into a chat panel, character stage, and systems panel.
- Added local Kokoro ONNX TTS with automatic model download on first use.
- Added screen capture + screen commentary support.
- Added explicit local commands for screen status, clipboard access, app opening, and shell execution.
- Added persistent settings for voice, screen access, and computer control.

## Requirements

- macOS
- Python 3.12+
- `pygame-ce`, `pillow`, `requests`, `kokoro-onnx`, `soundfile`
- Ollama optional, but recommended for better responses

## Install

```bash
git clone https://github.com/gabriel/RikoCompanion.git
cd RikoCompanion
python3 -m venv venv
source venv/bin/activate
pip install pygame-ce pillow requests kokoro-onnx soundfile
```

## Run

```bash
./run.sh
```

Or:

```bash
source venv/bin/activate
python main.py
```

On first real voice playback, Riko downloads the free Kokoro int8 model and voice pack into `models/tts/`.

## Voice

Riko uses Kokoro ONNX for real offline TTS. The default voice is `af_heart`, which fits the current visual design better than the flatter Piper-style voices and avoids cloud costs entirely.

## Screen + Computer Access

Riko can:

- `/screen` capture the current screen and comment on it
- `/status` show battery + frontmost app/window
- `/clipboard` read clipboard text
- `/open Safari` open an app, file, or URL
- `/shell pwd` run an explicit shell command

Screen commentary works best if Ollama has a local vision-capable model installed. The recommended local model for Apple Silicon laptops is `gemma3:4b` because it is an official Ollama multimodal model and lighter than the larger vision options. Without a vision model, Riko still captures the screen and reports frontmost app/window context.

## Shortcuts

- `Enter`: send message
- `F1`: scan screen
- `F2`: toggle voice
- `F3`: toggle screen access
- `F4`: toggle computer control
- `Cmd/Ctrl + L`: clear chat
- `Esc`: quit

## Ollama

If Ollama is running, Riko uses it automatically.

Recommended local vision install:

```bash
ollama pull gemma3:4b
```

Riko will prefer `gemma3:4b` first, then other detected local vision models.

## Files

- `main.py`: app + UI
- `riko_brain.py`: dialogue + command routing
- `riko_services.py`: TTS, screen capture, system tools
- `sprites.py`: sprite loading/animation
