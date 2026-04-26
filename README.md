# Nils Companion

Nils Companion is a local macOS desktop companion built with `pygame`. It now has a proper desktop UI, offline neural TTS with voice cloning, screen awareness, and explicit local computer controls instead of just basic text replies.

## Requirements

- macOS
- Python 3.12+
- `pygame-ce`, `pillow`, `requests`, `qwen-tts`, `torch`, `soundfile`, `mlx-whisper`
- Ollama optional, but recommended for better responses

## Install

```bash
git clone https://github.com/gabriel/RikoCompanion.git
cd RikoCompanion
python3 -m venv venv
source venv/bin/activate
pip install pygame-ce pillow requests qwen-tts torch soundfile mlx-whisper
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

## Voice + Voice Cloning

Nils uses Qwen3-TTS for offline TTS with voice cloning support.

**Default voice**: Built-in default voice

**Voice cloning**: To clone a voice from an audio file:
```
/clone path/to/voice.wav
```

The audio file should be 3-30 seconds of clean speech. The cloned voice is saved to `models/tts/voice_clone.wav`.
If `path/to/voice.txt` exists next to the audio file, Nils uses it as the reference transcript for higher-fidelity ICL cloning.
If there is no sidecar transcript, Nils now tries to auto-transcribe the reference audio with `mlx-whisper` or `whisper` before falling back to x-vector clone mode.
Nils also ships with `nils-ref.wav` as a built-in voice reference, so TTS has a working fallback voice before you import a custom clone.

**Voice cycling**: Press the "Change Voice" button or the voice will cycle between default and cloned voice.

## Screen + Computer Access

Nils can:
- `/screen` capture the current screen and comment on it
- `/status` show battery + frontmost app/window
- `/clipboard` read clipboard text
- `/open Safari` open an app, file, or URL
- `/shell pwd` run an explicit shell command
- `/clone voice.wav` set voice clone from audio file

Screen commentary works best if Ollama has a local vision-capable model installed. The recommended local model for Apple Silicon laptops is `gemma3:4b` because it is an official Ollama multimodal model and lighter than the larger vision options. Without a vision model, Nils still captures the screen and reports frontmost app/window context.

## Shortcuts

- `Enter`: send message
- `F1`: scan screen
- `F2`: toggle voice
- `F3`: toggle screen access
- `F4`: toggle computer control
- `Cmd/Ctrl + L`: clear chat
- `Esc`: quit

## Ollama

If Ollama is running, Nils uses it automatically.

Recommended local vision install:

```bash
ollama pull gemma3:4b
```

Nils will prefer `gemma3:4b` first, then other detected local vision models.

## Files

- `main.py`: app + UI
- `riko_brain.py`: dialogue + command routing
- `riko_services.py`: TTS, screen capture, system tools
- `sprites.py`: sprite loading/animation
