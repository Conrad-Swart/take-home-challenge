#!/bin/bash
#═══════════════════════════════════════════════════════
#  Clever Dictate — Installer v1.0
#  100% local voice-to-text for macOS (Apple Silicon)
#═══════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════════════════"
echo "  Clever Dictate — Installer"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Step 1: Check Apple Silicon ──────────────────────────
echo "Step 1: Checking system..."
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "ERROR: Clever Dictate requires Apple Silicon (M1/M2/M3/M4)."
    echo "Your system is $ARCH."
    exit 1
fi
echo "  Apple Silicon detected."

# ── Step 2: Check Python 3.13 ───────────────────────────
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python 3.13 not found."
    echo "Install from: https://www.python.org/downloads/"
    exit 1
fi
echo "  Python 3.13 found."

# ── Step 3: Check/install ffmpeg ─────────────────────────
echo ""
echo "Step 2: Checking dependencies..."
if ! command -v ffmpeg &>/dev/null && [ ! -f /opt/homebrew/bin/ffmpeg ]; then
    echo "  ffmpeg not found. Installing via Homebrew..."
    if ! command -v brew &>/dev/null; then
        echo "ERROR: Homebrew not installed. Install from: https://brew.sh"
        exit 1
    fi
    brew install ffmpeg
fi
echo "  ffmpeg ready."

# ── Step 4: Install Python packages ─────────────────────
echo ""
echo "Step 3: Installing Python packages..."
arch -arm64 $PYTHON -m pip install --quiet --upgrade \
    mlx-whisper mlx-lm pynput pyobjc-framework-Cocoa numpy 2>&1 | tail -3
echo "  Packages installed."

# ── Step 5: Copy scripts ────────────────────────────────
echo ""
echo "Step 4: Installing Clever Dictate..."
mkdir -p ~/.local/bin
cp "$SCRIPT_DIR/dictate.py" ~/.local/bin/dictate.py
cp "$SCRIPT_DIR/dictate_tray.py" ~/.local/bin/dictate_tray.py
chmod +x ~/.local/bin/dictate.py ~/.local/bin/dictate_tray.py
echo "  Scripts installed to ~/.local/bin/"

# ── Step 6: Copy app bundle ─────────────────────────────
if [ -d "/Applications/Clever Dictate.app" ]; then
    echo "  Clever Dictate.app already exists — updating..."
    rm -rf "/Applications/Clever Dictate.app"
fi
cp -r "$SCRIPT_DIR/Clever Dictate.app" /Applications/
echo "  App installed to /Applications/"

# ── Step 7: Install Whisper model ────────────────────────
echo ""
echo "Step 5: Installing Whisper AI model..."
MODEL_SRC="$SCRIPT_DIR/models/whisper-small.en-mlx"
if [ -d "$MODEL_SRC" ]; then
    # Copy to HuggingFace cache so mlx_whisper finds it
    HF_DIR="$HOME/.cache/huggingface/hub/models--mlx-community--whisper-small.en-mlx"
    mkdir -p "$HF_DIR/snapshots/local"
    cp "$MODEL_SRC"/* "$HF_DIR/snapshots/local/" 2>/dev/null
    # Create refs/main pointing to our snapshot
    mkdir -p "$HF_DIR/refs"
    echo "local" > "$HF_DIR/refs/main"
    echo "  Whisper model will download on first use (~460MB, one-time)."
else
    echo "  Whisper model not bundled — will download on first use (~460MB)."
fi

# ── Step 8: Create settings ─────────────────────────────
echo ""
echo "Step 6: Creating settings..."
mkdir -p ~/.local/share/dictate
if [ ! -f ~/.local/share/dictate/settings.json ]; then
    echo '{"cleanup_level": 25}' > ~/.local/share/dictate/settings.json
    echo "  Default settings created."
else
    echo "  Settings already exist — keeping yours."
fi

# ── Step 9: Accessibility reminder ───────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Installation Complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "IMPORTANT — One manual step required:"
echo ""
echo "  1. Open System Settings > Privacy & Security > Accessibility"
echo "  2. Click + and add your terminal app (VS Code, Terminal, iTerm, etc.)"
echo "  3. Make sure it's toggled ON"
echo ""
echo "Then open Clever Dictate from Applications or Launchpad."
echo "Hold Right Option to dictate. Release to paste."
echo ""
echo "Enjoy!"
