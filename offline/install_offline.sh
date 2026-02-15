#!/usr/bin/env bash
# Run this script on the AIRGAPPED PC (after copying the full project + offline/vendor).
# Installs Python packages from offline/vendor/wheels and prepares npm.
# Run from the project root: ./offline/install_offline.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR="$SCRIPT_DIR/vendor"
cd "$PROJECT_ROOT"

echo "=== Game Agent offline install ==="
echo "Project root: $PROJECT_ROOT"
echo ""

if [[ ! -d "$VENDOR/wheels" ]] || [[ -z "$(ls -A "$VENDOR/wheels" 2>/dev/null)" ]]; then
  echo "Error: $VENDOR/wheels not found or empty. Run download_bundle.sh on an online machine first."
  exit 1
fi

# ----- 1. Python: install into a venv (avoids PEP 668 externally-managed-environment) -----
echo "[1/2] Installing Python packages from offline wheels..."
echo "  (On Linux/WSL, PyAudio needs PortAudio: sudo apt install portaudio19-dev)"
VENV_DIR="$VENDOR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
  echo "  Created venv at $VENV_DIR"
fi
if [[ -f "$VENV_DIR/bin/pip" ]]; then
  VENV_PIP="$VENV_DIR/bin/pip"
else
  VENV_PIP="$VENV_DIR/Scripts/pip.exe"
fi
# Install core first (includes LLM, backend, Whisper) so web demo always works
"$VENV_PIP" install --no-index --find-links "$VENDOR/wheels" -r "$SCRIPT_DIR/requirements-offline-minimal.txt"
# Then try PyAudio (needs system PortAudio on Linux); optional for web demo
if ! "$VENV_PIP" install --no-index --find-links "$VENDOR/wheels" pyaudio>=0.2.14; then
  echo ""
  echo "  Note: PyAudio could not be installed (on Linux/WSL: sudo apt install portaudio19-dev)."
  echo "  Web demo (./offline/run_all.sh) works without it; only the desktop PTT UI (python main.py) needs PyAudio."
fi

# ----- 2. npm: install from cache (or use existing node_modules) -----
echo "[2/2] Preparing frontend (npm)..."
cd "$PROJECT_ROOT/frontend"
if [[ -d "$VENDOR/npm_cache" ]]; then
  npm install --prefer-offline --cache "$VENDOR/npm_cache" --no-audit --no-fund
else
  echo "Warning: no npm cache at $VENDOR/npm_cache; if node_modules exists from bundle copy, you can skip. Otherwise run download_bundle.sh on an online machine."
  if [[ ! -d node_modules ]]; then
    echo "Error: no node_modules and no npm cache. Cannot install frontend."
    exit 1
  fi
fi
cd "$PROJECT_ROOT"

# ----- Config -----
if [[ ! -f "$SCRIPT_DIR/offline_config.env" ]]; then
  if [[ -f "$SCRIPT_DIR/offline_config.env.example" ]]; then
    cp "$SCRIPT_DIR/offline_config.env.example" "$SCRIPT_DIR/offline_config.env"
    echo "Created $SCRIPT_DIR/offline_config.env from example. Edit it to set LLM/Whisper paths if needed."
  fi
fi

echo ""
echo "=== Install done. ==="
echo "Python packages are in: $VENV_DIR"
echo "To run the full stack (LLM server + backend + frontend):"
echo "  ./offline/run_all.sh"
echo "(run_all.sh uses this venv automatically)"
