#!/usr/bin/env bash
# Run this script on a machine WITH internet to download all dependencies into
# offline/vendor/. Then copy the entire project folder to the airgapped PC.
# Use LF line endings (not CRLF). If you see \r errors, run: sed -i 's/\r$//' offline/download_bundle.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR="$SCRIPT_DIR/vendor"
cd "$PROJECT_ROOT"

echo "=== Game Agent offline bundle download ==="
echo "Project root: $PROJECT_ROOT"
echo "Vendor dir:   $VENDOR"
echo ""

# ----- Config: change these to use a different LLM or Whisper model -----
# See CONFIG.md for details.
WHISPER_MODEL="${WHISPER_MODEL:-large-v3-turbo}"
# GGUF URL: use a direct link to the .gguf file (e.g. from Hugging Face).
GGUF_URL="${GGUF_URL:-https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf}"
GGUF_NAME="${GGUF_NAME:-qwen2.5-3b-instruct-q4_k_m.gguf}"

mkdir -p "$VENDOR/wheels" "$VENDOR/whisper_models" "$VENDOR/llm_models" "$VENDOR/npm_cache"

# ----- 1. Python wheels -----
echo "[1/4] Downloading Python wheels..."
pip download -d "$VENDOR/wheels" -r "$SCRIPT_DIR/requirements-offline.txt"

# ----- 2. Whisper model: use a venv so we don't touch system Python (PEP 668) -----
echo "[2/4] Downloading Whisper model: $WHISPER_MODEL"
VENV_DIR="$VENDOR/.venv_download"
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
if [[ -f "$VENV_DIR/bin/pip" ]]; then
  VENV_PIP="$VENV_DIR/bin/pip"
  VENV_PY="$VENV_DIR/bin/python"
else
  VENV_PIP="$VENV_DIR/Scripts/pip.exe"
  VENV_PY="$VENV_DIR/Scripts/python.exe"
fi
"$VENV_PIP" install --no-index --find-links "$VENDOR/wheels" faster-whisper
"$VENV_PY" "$SCRIPT_DIR/_download_whisper.py" "$VENDOR/whisper_models" "$WHISPER_MODEL"

# ----- 3. GGUF model -----
echo "[3/4] Downloading GGUF model..."
GGUF_PATH="$VENDOR/llm_models/$GGUF_NAME"
if command -v wget >/dev/null 2>&1; then
  wget -q --show-progress -O "$GGUF_PATH" "$GGUF_URL"
elif command -v curl >/dev/null 2>&1; then
  curl -# -L -o "$GGUF_PATH" "$GGUF_URL"
else
  echo "Error: need wget or curl to download GGUF"
  exit 1
fi
echo "Saved to $GGUF_PATH"

# ----- 4. npm dependencies -----
echo "[4/4] Downloading npm dependencies..."
cd "$PROJECT_ROOT/frontend"
npm install --cache "$VENDOR/npm_cache"
cd "$PROJECT_ROOT"

echo ""
echo "=== Done. Vendor contents: ==="
echo "  wheels:         $(ls "$VENDOR/wheels" 2>/dev/null | wc -l) files"
echo "  whisper_models: $(ls "$VENDOR/whisper_models" 2>/dev/null | wc -l) items"
echo "  llm_models:     $GGUF_NAME"
echo "  npm_cache:      populated"
echo ""
echo "Next: copy the entire project folder to the airgapped PC, then run:"
echo "  ./offline/install_offline.sh"
echo "  ./offline/run_all.sh"
echo ""
echo "To use a different Whisper or LLM model, see offline/CONFIG.md"
