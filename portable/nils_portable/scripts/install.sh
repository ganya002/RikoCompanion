#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo " Nils Companion - Portable Installer"
echo "=========================================="
echo ""

REQUIRED_MIN_MACOS="13.0"
MIN_PYTHON="3.12"

check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        echo "ERROR: This portable package only supports macOS."
        exit 1
    fi
    
    local macos_version
    macos_version=$(sw_vers -productVersion)
    local major_minor
    major_minor=$(echo "$macos_version" | cut -d. -f1,2)
    
    if [[ - "$major_minor" < "$REQUIRED_MIN_MACOS" ]]; then
        echo "ERROR: macOS $REQUIRED_MIN_MACOS or later required. You have macOS $macos_version"
        exit 1
    fi
    echo "[OK] macOS version check passed ($macos_version)"
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
        PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
        
        if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 12 ]]; then
            echo "WARNING: Python $PYTHON_VERSION detected, but Python 3.12+ required."
            echo "         Installing Python via Homebrew..."
            install_brew_python
        else
            echo "[OK] Python $PYTHON_VERSION detected"
        fi
    else
        echo "Python not found. Installing via Homebrew..."
        install_brew_python
    fi
    
    export PATH="$HOME/.local/bin:$PATH"
}

install_brew_python() {
    if ! command -v brew &> /dev/null; then
        echo ""
        echo "=========================================="
        echo " Installing Homebrew..."
        echo "=========================================="
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    echo "Installing Python 3.12 via Homebrew..."
    brew install python@3.12
    
    alias python3="$HOME/homebrew/bin/python3"
    python3 --version || true
}

check_homebrew() {
    if ! command -v brew &> /dev/null; then
        echo ""
        echo "=========================================="
        echo " Installing Homebrew..."
        echo "=========================================="
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    echo "[OK] Homebrew available"
}

check_screen_capture_permission() {
    if ! sqlite3 "/Library/Application Support/com.apple.TCC/TCC.db" "SELECT count(*) FROM access WHERE service='screen_capture' AND auth_value='1';" 2>/dev/null | grep -q 1; then
        echo ""
        echo "=========================================="
        echo " Screen Recording Permission Required"
        echo "=========================================="
        echo "Please grant Screen Recording permission to Terminal in:"
        echo "  System Settings > Privacy & Security > Screen Recording"
        echo ""
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        echo "After granting permission, press Enter to continue..."
        read -r
    fi
    echo "[OK] Screen capture permission available"
}

check_ollama() {
    if pgrep -x "ollama" > /dev/null; then
        echo "[OK] Ollama is running"
    else
        echo "[INFO] Ollama not running. Nils will use rule-based responses."
        echo "       To enable AI responses: brew install ollama && ollama serve"
    fi
}

install_dependencies() {
    echo ""
    echo "=========================================="
    echo " Installing Python dependencies..."
    echo "=========================================="
    
    PYTHON_BIN="python3"
    if [[ -f "$HOME/homebrew/opt/python@3.12/bin/python3" ]]; then
        PYTHON_BIN="$HOME/homebrew/opt/python@3.12/bin/python3"
    fi
    
    cd "$SCRIPT_DIR/.."
    
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        $PYTHON_BIN -m venv venv
    fi
    
    source venv/bin/activate
    
    echo "Installing packages: pygame-ce, pillow, requests, soundfile..."
    pip install --upgrade pip
    pip install pygame-ce pillow requests soundfile
    
    echo ""
    echo "=========================================="
    echo " Installing AI models (large download)..."
    echo "=========================================="
    echo "This may take a while for first-time setup."
    echo ""
    
    echo "Installing qwen-tts (Qwen3-TTS)..."
    pip install qwen-tts
    
    echo ""
    echo "Installing torch (MLX-optimized for Apple Silicon)..."
    if [[ "$(uname -m)" == "arm64" ]]; then
        pip install torch --index-url https://download.pytorch.org/whl/cpu
    else
        pip install torch
    fi
    
    echo ""
    echo "Installing mlx-whisper for voice cloning..."
    pip install mlx-whisper || pip install faster-whisper || echo "[INFO] Whisper not available, voice cloning may use x-vector mode"
    
    echo ""
    echo "[OK] Dependencies installed successfully"
}

finalize() {
    echo ""
    echo "=========================================="
    echo " Installation Complete!"
    echo "=========================================="
    echo ""
    echo "To run Nils:"
    echo "  cd \"$(dirname "$SCRIPT_DIR")\""
    echo "  ./nils_portable/run.sh"
    echo ""
    echo "First launch will download AI models (~3-5 GB)."
    echo ""
}

main() {
    check_macos
    check_homebrew
    check_python
    install_dependencies
    check_ollama
    check_screen_capture_permission
    finalize
}

main "$@"