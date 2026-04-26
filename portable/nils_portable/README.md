# Nils Companion - Portable Edition

A self-contained portable package for Nils desktop companion with automatic installation.

## What's Included

- Nils Companion app (main.py and all Python modules)
- AI Models: Qwen3-TTS (voice synthesis) + Kokoro TTS voices
- Voice reference audio (nils-ref.wav)
- Sprite and animation files
- Automatic dependency installer (Homebrew, Python, pip packages)

## Quick Start

1. Copy this entire folder to your MacBook M2 Max (via USB or any method)
2. Open Terminal and navigate to the folder:
   ```bash
   cd path/to/nils_portable
   ```
3. Run the installer:
   ```bash
   ./run.sh
   ```
4. Follow any prompts (System Settings permissions may appear)

## First Run

The first time you run Nils, it will:
1. Check for Homebrew (installs if missing)
2. Install Python 3.12 (if needed)
3. Install all Python dependencies (~2-4 GB download)
4. Download the Qwen3-TTS AI model (~2 GB)
5. Set up the virtual environment

This takes 10-30 minutes depending on your internet speed.

## Requirements

- macOS 13.0 (Ventura) or later
- Apple Silicon (M1/M2/M3/M4) recommended for best performance
- ~10 GB free disk space (for AI models)

## Features

- **Voice**: Offline neural TTS with Qwen3-TTS + voice cloning
- **Vision**: Screen capture and analysis (requires Ollama for full AI vision)
- **Commands**: /screen, /status, /clipboard, /open, /shell
- **Ollama**: Optional but recommended for AI responses
  ```bash
  brew install ollama
  ollama serve
  ollama pull dolphin3:8b
  ```

## Keyboard Shortcuts

- `Enter`: Send message
- `F1`: Scan screen
- `F2`: Toggle voice
- `F3`: Toggle screen access
- `F4`: Toggle computer control
- `Cmd/Ctrl+L`: Clear chat
- `Esc`: Quit

## Troubleshooting

### "Cannot open app because it requires Rosetta"
Make sure you're on macOS 13+ and using the arm64 version.

### Voice not working
Run the installer again: `./run.sh`

### Ollama not responding
Install Ollama: `brew install ollama && ollama serve`

## License

This is the Nils Companion app. Use responsibly.