#!/usr/bin/env bash
# Run this on the airgapped PC to start: (1) LLM server if needed, (2) backend, (3) frontend.
# If an OpenAI-compatible LLM is already running at localhost:1234/v1 (e.g. LM Studio), it is used and llama-cpp-python is not started.
# Run from project root: ./offline/run_all.sh
# Ensure install_offline.sh has been run first.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR="$SCRIPT_DIR/vendor"
cd "$PROJECT_ROOT"

# Load config (paths for GGUF, ports, etc.); strip \r so CRLF line endings work under bash
if [[ -f "$SCRIPT_DIR/offline_config.env" ]]; then
  set -a
  source <(tr -d '\r' < "$SCRIPT_DIR/offline_config.env")
  set +a
fi
LLM_GGUF_PATH="${LLM_GGUF_PATH:-$SCRIPT_DIR/vendor/llm_models/qwen2.5-3b-instruct-q4_k_m.gguf}"
LM_STUDIO_MODEL="${LM_STUDIO_MODEL:-qwen2.5-3b-instruct}"
LLM_SERVER_PORT="${LLM_SERVER_PORT:-1234}"
LLM_CHAT_FORMAT="${LLM_CHAT_FORMAT:-}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

export LM_STUDIO_BASE_URL="http://localhost:${LLM_SERVER_PORT}/v1"
export LM_STUDIO_MODEL
export WHISPER_DOWNLOAD_ROOT="$VENDOR/whisper_models"
export WHISPER_DEVICE="${WHISPER_DEVICE:-cpu}"
export WHISPER_MODEL="${WHISPER_MODEL:-large-v3-turbo}"

# Use offline venv if install_offline.sh was run (avoids system Python / PEP 668)
if [[ -f "$VENDOR/.venv/bin/python" ]]; then
  PYTHON_CMD="$VENDOR/.venv/bin/python"
  VENV_PIP="$VENDOR/.venv/bin/pip"
elif [[ -f "$VENDOR/.venv/Scripts/python.exe" ]]; then
  PYTHON_CMD="$VENDOR/.venv/Scripts/python.exe"
  VENV_PIP="$VENDOR/.venv/Scripts/pip.exe"
else
  PYTHON_CMD="python3"
  VENV_PIP="pip"
fi

# Ensure backend dependency python-multipart is in venv (from offline wheels if present)
if [[ -d "$VENDOR/wheels" ]] && [[ -n "$VENV_PIP" ]]; then
  "$VENV_PIP" install --no-index --find-links "$VENDOR/wheels" python-multipart >/dev/null 2>&1 || true
fi

# Check if an LLM server is already running (e.g. LM Studio) at the configured port
# From WSL, 127.0.0.1 is WSL's loopback; LM Studio on Windows is reachable at the Windows host IP.
LLM_PID=""
LLM_HOST="127.0.0.1"
DEBUG_LOG="$PROJECT_ROOT/.cursor/debug.log"
mkdir -p "$(dirname "$DEBUG_LOG")" 2>/dev/null || true
# Use /v1/models only (LM Studio does not support GET /health and logs an error)
_llm_reachable() {
  curl -s -o /dev/null --connect-timeout 2 "http://${1}:${LLM_SERVER_PORT}/v1/models" 2>/dev/null
}
IN_WSL=""; grep -qi microsoft /proc/version 2>/dev/null && IN_WSL="yes"
if _llm_reachable "$LLM_HOST"; then
  :
elif [[ "$IN_WSL" == "yes" ]]; then
  # Try nameserver (resolv.conf) then default gateway; either can be the Windows host in WSL2
  WSL_NS="$(grep -E '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | head -1)"
  WSL_GW="$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)"
  # #region agent log
  echo "{\"hypothesisId\":\"H1\",\"location\":\"run_all.sh:wsl_fallback\",\"message\":\"wsl_host_lookup\",\"data\":{\"nameserver\":\"$WSL_NS\",\"gateway\":\"$WSL_GW\",\"port\":\"$LLM_SERVER_PORT\"},\"timestamp\":$(date +%s)000}" >> "$DEBUG_LOG" 2>/dev/null || true
  # #endregion
  for WSL_HOST in "$WSL_NS" "$WSL_GW"; do
    [[ -z "$WSL_HOST" ]] && continue
    if _llm_reachable "$WSL_HOST"; then
      LLM_HOST="$WSL_HOST"
      break
    fi
  done
fi
# #region agent log
echo "{\"hypothesisId\":\"H1\",\"location\":\"run_all.sh:llm_check\",\"message\":\"llm_host_resolved\",\"data\":{\"LLM_HOST\":\"$LLM_HOST\",\"port\":\"$LLM_SERVER_PORT\",\"in_wsl\":\"$IN_WSL\"},\"timestamp\":$(date +%s)000}" >> "$DEBUG_LOG" 2>/dev/null || true
# #endregion
if _llm_reachable "$LLM_HOST"; then
  export LM_STUDIO_BASE_URL="http://${LLM_HOST}:${LLM_SERVER_PORT}/v1"
  echo "=== LLM already running at ${LLM_HOST}:$LLM_SERVER_PORT (e.g. LM Studio) — skipping llama-cpp-python ==="
  # #region agent log
  echo "{\"hypothesisId\":\"H3\",\"location\":\"run_all.sh:branch\",\"message\":\"llm_detected\",\"data\":{\"branch\":\"skip_llama\",\"host\":\"$LLM_HOST\"},\"timestamp\":$(date +%s)000}" >> "$DEBUG_LOG" 2>/dev/null || true
  # #endregion
else
  # #region agent log
  echo "{\"hypothesisId\":\"H3\",\"location\":\"run_all.sh:branch\",\"message\":\"llm_not_detected\",\"data\":{\"branch\":\"start_llama\"},\"timestamp\":$(date +%s)000}" >> "$DEBUG_LOG" 2>/dev/null || true
  # #endregion
  # Resolve GGUF path and start llama-cpp-python
  if [[ "$LLM_GGUF_PATH" != /* ]]; then
    LLM_GGUF_PATH="$PROJECT_ROOT/$LLM_GGUF_PATH"
  fi
  if [[ ! -f "$LLM_GGUF_PATH" ]]; then
    echo "Error: GGUF model not found at $LLM_GGUF_PATH"
    echo "Edit offline/offline_config.env and set LLM_GGUF_PATH to your model file."
    echo "Or start LM Studio (or another OpenAI-compatible server) on port $LLM_SERVER_PORT and run this script again."
    exit 1
  fi
  echo "Starting LLM server (llama-cpp-python)..."
  LLM_SERVER_CMD=("$PYTHON_CMD" -m llama_cpp.server --model "$LLM_GGUF_PATH" --port "$LLM_SERVER_PORT" --n_ctx 4096)
  [[ -n "$LLM_CHAT_FORMAT" ]] && LLM_SERVER_CMD+=(--chat_format "$LLM_CHAT_FORMAT")
  "${LLM_SERVER_CMD[@]}" &
  LLM_PID=$!
  echo "  LLM server PID: $LLM_PID"
  for i in {1..60}; do
    if curl -s -o /dev/null "http://127.0.0.1:${LLM_SERVER_PORT}/v1/models" 2>/dev/null; then
      echo "  LLM server ready."
      break
    fi
    if ! kill -0 $LLM_PID 2>/dev/null; then
      echo "Error: LLM server process exited."
      exit 1
    fi
    sleep 1
  done
fi

echo "=== Starting Game Agent (LLM + Backend + Frontend) ==="
echo "  Python:       $PYTHON_CMD"
echo "  LLM:          http://localhost:${LLM_SERVER_PORT}/v1"
echo "  Backend:      port $BACKEND_PORT"
echo "  Frontend:     port $FRONTEND_PORT"
echo "  Whisper:      $WHISPER_MODEL ($WHISPER_DEVICE)"
echo ""

# Start backend
echo "Starting backend..."
"$PYTHON_CMD" -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"
sleep 2

# Start frontend (dev server so API proxy works)
echo "Starting frontend..."
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"
echo "  Frontend PID: $FRONTEND_PID"
echo ""
echo "=== All services running. ==="
echo "  Open: http://localhost:$FRONTEND_PORT"
echo "  API:  http://localhost:$BACKEND_PORT"
echo "  Press Ctrl+C to stop all."
echo ""

cleanup() {
  echo "Stopping services..."
  kill $FRONTEND_PID 2>/dev/null || true
  kill $BACKEND_PID 2>/dev/null || true
  [[ -n "$LLM_PID" ]] && kill $LLM_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM
wait
