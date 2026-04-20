# Riko Companion

A cute desktop companion app featuring Riko, an 18-year-old girl who lives on your MacBook. Uses local AI (Ollama) for conversations.

## Requirements

- macOS
- Python 3.12+
- Ollama (optional, for smarter conversations)

## Installation

### 1. Clone the repo
```bash
git clone https://github.com/gabriel/RikoCompanion.git
cd RikoCompanion
```

### 2. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install pygame-ce pillow requests
```

### 4. Install Ollama (optional but recommended)

```bash
# Install Ollama
brew install ollama

# Start Ollama
ollama serve

# In a new terminal, pull a model (dolphin3:8b works great):
ollama pull dolphin3:8b
```

## Running

```bash
source venv/bin/activate
python main.py
```

If Ollama is running, Riko will use it for conversations. If not, she'll use basic responses.

## Troubleshooting

### "Ollama not connected"
Make sure Ollama is running:
```bash
ollama serve
```

### App doesn't start
Make sure your virtual environment is activated:
```bash
source venv/bin/activate
```

## Files

- `main.py` - Main app
- `riko_brain.py` - Response engine
- `sprites.py` - Sprite/animation handler
- `riko.png` - Static Riko image
- `animation.gif` - Riko animation (optional)
- `riko_history.json` - Chat history (auto-created)

## Controls

- Type in the text box and press Enter to send
- Press Escape to quit

Made with ❤️ for Gabriel