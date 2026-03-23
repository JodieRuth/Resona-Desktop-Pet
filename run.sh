#!/bin/bash

cd "$(dirname "$0")"

echo "[Resona] Starting Resona Desktop Pet..."


PYTHON_EXEC=""

if [ -f "runtime/python" ]; then
    PYTHON_EXEC="./runtime/python"
    echo "[Resona] Using portable runtime Python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_EXEC="./venv/bin/python"
    echo "[Resona] Using virtual environment Python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXEC="python3"
    echo "[Resona] Using system python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_EXEC="python"
    echo "[Resona] Using system python"
else
    echo "[ERROR] No valid Python environment found!"
    echo "Please run setup.sh or install Python manually."
    exit 1
fi


if command -v ffmpeg >/dev/null 2>&1; then
    echo "[Resona] Using system FFmpeg"
elif [ -f "ffmpeg/bin/ffmpeg" ]; then
    export PATH="$(pwd)/ffmpeg/bin:$PATH"
    echo "[Resona] Added local FFmpeg to PATH"
else
    echo "[WARNING] FFmpeg not found in system PATH or local directory!"
    echo "Audio functions may fail. Please install ffmpeg using your package manager:"
    echo "  Debian/Ubuntu: sudo apt install ffmpeg"
    echo "  Fedora/RHEL: sudo dnf install ffmpeg"
    echo "  Arch: sudo pacman -S ffmpeg"
    echo "  macOS (Homebrew): brew install ffmpeg"
    echo "You can also copy ffmpeg executable to ffmpeg/bin/ffmpeg in this directory."
fi

echo "[Resona] Using environment: $PYTHON_EXEC"
# 创建临时文件来捕获错误输出
TEMP_DIR="${TMPDIR:-/tmp}"
ERROR_OUTPUT=$(mktemp 2>/dev/null || echo "$TEMP_DIR/resona_error_$$.log")
trap "rm -f '$ERROR_OUTPUT' 2>/dev/null" EXIT INT TERM

echo "[Resona] Starting main program..."
echo "════════════════════════════════════════"

$PYTHON_EXEC main.py "$@" 2>"$ERROR_OUTPUT"
EXIT_CODE=$?

echo "════════════════════════════════════════"

if [ $EXIT_CODE -eq 0 ]; then
    echo "[Resona] Program exited successfully."
    exit 0
else
    echo "[Resona] Program failed with exit code: $EXIT_CODE"
    echo
    
    if [ -s "$ERROR_OUTPUT" ]; then
        echo "════════════════════════════════════════"
        echo "ERROR OUTPUT:"
        echo "════════════════════════════════════════"
        cat "$ERROR_OUTPUT"
        echo "════════════════════════════════════════"
    else
        echo "[Info] No error output captured."
    fi
    
    echo
    echo "════════════════════════════════════════"
    echo "TROUBLESHOOTING SUGGESTIONS:"
    echo "════════════════════════════════════════"
    echo "1. Check if all dependencies are installed:"
    echo "   Run: $PYTHON_EXEC -m pip install -r requirements.txt"
    echo
    echo "2. Check if virtual environment is activated (if using one):"
    echo "   Run: source venv/bin/activate  # For bash/zsh"
    echo
    echo "3. Verify Python installation:"
    echo "   Run: $PYTHON_EXEC --version"
    echo
    echo "4. Check for missing system libraries:"
    echo "   - PortAudio (for audio input): sudo apt install portaudio19-dev"
    echo "   - Qt6 (for GUI): sudo apt install qt6-base-dev"
    echo
    echo "5. If using portable Python runtime, ensure it's properly extracted."
    echo
    echo "6. Try running with verbose output for more details:"
    echo "   $PYTHON_EXEC -c \"import sys; print('Python path:', sys.path)\""
    echo "════════════════════════════════════════"
    
    exit $EXIT_CODE
fi