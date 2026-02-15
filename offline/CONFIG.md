# Offline bundle: where to change LLM and Whisper models

Use this when you switch to a different **LLM** (GGUF) or **Whisper** (ASR) model on the airgapped PC.

**Requirements on the airgapped PC:** Python 3.10+, Node.js/npm, and **ffmpeg** (used by the backend for `/transcribe` with uploaded audio). Install ffmpeg with your system package manager if needed; it is not bundled in `vendor/`.

---

## Switching the LLM (GGUF) model

The app talks to an OpenAI-compatible API (by default the one started by `run_all.sh` using llama-cpp-python). The model file and name are configured in **one place**.

### 1. Config file (airgapped PC)

Edit **`offline/offline_config.env`** (copy from `offline_config.env.example` if it doesn’t exist):

```bash
# Path to your GGUF file (relative to project root or absolute)
LLM_GGUF_PATH=offline/vendor/llm_models/your-model.gguf

# Model name as shown in the API (backend uses this when calling the LLM)
LM_STUDIO_MODEL=your-model-name
```

- **`LLM_GGUF_PATH`** – Path to the `.gguf` file. Use a path relative to the project root (e.g. `offline/vendor/llm_models/...`) or an absolute path.
- **`LM_STUDIO_MODEL`** – Name of the model as exposed by the server (often the filename without `.gguf`, or the name the server reports). The backend sends this as the `model` in chat requests.
- **`LLM_CHAT_FORMAT`** (optional) – Chat format for the llama-cpp-python server. **Leave unset** (server default). Setting `chatml` can make tool calling worse (model may output `create_target(Village)` in content instead of structured tool_calls). See “LLM behavior and alternatives” below.

After changing, run **`./offline/run_all.sh`** again (no need to re-run `install_offline.sh` unless you add new Python/npm deps).

### LLM behavior and alternatives (offline vs LM Studio)

When you run the **offline** stack, the LLM is served by **llama-cpp-python** instead of LM Studio. You may see more “tool call in content” (model outputs the call as text) or occasional misunderstanding. **LM Studio** is tuned for the OpenAI API and often handles tool/function calling more reliably.

**What the backend does:** It has a **fallback parser** that runs tools when the model puts a call in the message text, in either form:

- `<tool_call>{"name": "create_dragon_spot", "arguments": {...}}</tool_call>`
- Plain style: `create_target(Village)` or `move_knight("North Ridge", "Sir Roland")`

So many text-style tool calls still execute correctly.

**If you need better behavior on the offline PC:**

1. **Leave `LLM_CHAT_FORMAT` unset** – the server default often works better than forcing `chatml`.
2. **Use a larger GGUF** (e.g. Qwen2.5-7B-Instruct) in the bundle if the machine can run it; tool use is usually more reliable.
3. **Alternative: run LM Studio on the offline PC** – install LM Studio from an installer (e.g. on a USB stick), copy your GGUF into it, load the model and start the server. Point the app at `http://localhost:1234/v1` as usual. No llama-cpp-python needed; tool calling will match your “regular” deployment.
4. **Alternative: Ollama** – install Ollama on the offline PC and use a model that supports tools; it can expose an OpenAI-compatible API. You’d need to bring the Ollama installer and model files for offline use.

### 2. Download script (online PC, when adding a new model to the bundle)

To put a **different GGUF** in the bundle, edit **`offline/download_bundle.sh`** before running it:

```bash
# Example: different model and URL
GGUF_URL="https://huggingface.co/.../resolve/main/your-model.gguf"
GGUF_NAME="your-model.gguf"
```

Then run `./offline/download_bundle.sh`, copy the project (including `offline/vendor/`) to the airgapped PC, and in **`offline_config.env`** set:

- `LLM_GGUF_PATH=offline/vendor/llm_models/your-model.gguf`
- `LM_STUDIO_MODEL=your-model-name`

---

## Switching the Whisper (ASR) model

Whisper is used for speech-to-text. You can change the model in two places.

### 1. Config / env (airgapped PC)

In **`offline/offline_config.env`** (or in the environment when you run the app):

```bash
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cpu
```

Common **`WHISPER_MODEL`** values:

- `large-v3-turbo` – default, good balance of speed and quality
- `distil-large-v3` – faster, slightly less accurate
- `base`, `small`, `medium` – smaller/faster, lower quality
- `large-v3` – higher quality, slower

The app loads the model from **`offline/vendor/whisper_models`** if **`WHISPER_DOWNLOAD_ROOT`** is set (e.g. by `run_all.sh`). So only models that were downloaded into that folder (see below) are available offline.

### 2. Download script (online PC, when adding a new Whisper model)

To bundle a **different Whisper model**, set **`WHISPER_MODEL`** when running the download script:

```bash
WHISPER_MODEL=distil-large-v3 ./offline/download_bundle.sh
```

That will download the chosen model into `offline/vendor/whisper_models/`. Then copy the project to the airgapped PC and set the same **`WHISPER_MODEL`** in **`offline_config.env`**.

---

## Summary

| What you change | Where to change it |
|-----------------|--------------------|
| **LLM model file** (which GGUF runs) | `offline/offline_config.env` → `LLM_GGUF_PATH` |
| **LLM model name** (name sent to API) | `offline/offline_config.env` → `LM_STUDIO_MODEL` |
| **Which GGUF to put in the bundle** | `offline/download_bundle.sh` → `GGUF_URL`, `GGUF_NAME` |
| **Whisper model** (which ASR model is used) | `offline/offline_config.env` → `WHISPER_MODEL` |
| **Which Whisper model to download** | `WHISPER_MODEL=... ./offline/download_bundle.sh` |

All of these are in the **`offline/`** folder and **`offline_config.env`**; no need to edit the main app code under `backend/`, `main.py`, or `audio_listener.py` for normal model switching.
