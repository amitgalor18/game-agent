# Offline / airgapped bundle

Run the Game Agent demo on a machine **without internet** by pre-downloading all dependencies into one folder and copying the project.

## Workflow

### On a machine WITH internet

1. **Download everything into `offline/vendor/`:**
   ```bash
   # From project root
   chmod +x offline/download_bundle.sh
   ./offline/download_bundle.sh
   ```
   This downloads:
   - Python wheels (all pip dependencies, including llama-cpp-python server)
   - Whisper ASR model (default: `large-v3-turbo`)
   - One GGUF LLM model (default: Qwen2.5-3B-Instruct Q4_K_M)
   - npm dependencies (into cache + `frontend/node_modules`)

2. **Copy the entire project** (including `offline/vendor/` and `frontend/node_modules`) to the airgapped PC (USB, shared drive, etc.).

### On the airgapped PC

1. **Install from the bundle (no network):**
   ```bash
   chmod +x offline/install_offline.sh offline/run_all.sh
   ./offline/install_offline.sh
   ```
   This installs Python packages from `offline/vendor/wheels` and prepares npm. It will create `offline/offline_config.env` from the example if missing.

2. **Run the full stack:**
   ```bash
   ./offline/run_all.sh
   ```
   This starts:
   - **LLM server** (llama-cpp-python, OpenAI-compatible) on port 1234
   - **Backend** (FastAPI) on port 8000
   - **Frontend** (Vite dev server) on port 5173

   Open **http://localhost:5173** in the browser.

## Changing LLM or Whisper model

See **[CONFIG.md](CONFIG.md)** for exactly where to change:
- Which GGUF file is used (path and model name)
- Which Whisper model is used
- How to add a different model to the bundle on the online machine

## Requirements on the airgapped PC

- **Python 3.10+**
- **Node.js** and **npm**
- **ffmpeg** (for backend `/transcribe` with uploaded audio) — see below to bundle it.
- **bash** (to run the scripts). On Windows use Git Bash or WSL, or adapt the steps to PowerShell.
- No internet required after copying the project and running `install_offline.sh`.

### Bundling ffmpeg (Windows / no system install)

Voice transcription needs **ffmpeg**. You can either install it on the PC (e.g. `winget install ffmpeg` or add it to PATH), or **bundle it** in the project so the backend uses it automatically:

1. Download a Windows build of ffmpeg (e.g. [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) “release essentials” or [BtbN](https://github.com/BtbN/FFmpeg-Builds/releases) — get the zip that contains `ffmpeg.exe`).
2. Create the folder **`offline/vendor/ffmpeg/`** in the project.
3. Put **`ffmpeg.exe`** (and optionally `ffprobe.exe`) inside that folder.

The backend looks for ffmpeg in this order: env **`FFMPEG_PATH`** (file or folder), then **`offline/vendor/ffmpeg/ffmpeg.exe`** (Windows) or **`offline/vendor/ffmpeg/ffmpeg`** (Linux), then system **PATH**. So once the exe is in `offline/vendor/ffmpeg/`, copy the project as usual and no system install is needed.

**Optional (desktop PTT only):** PyAudio is used only for the desktop push-to-talk UI (`python main.py`). To install it on Linux/WSL you need the PortAudio dev library first: `sudo apt install portaudio19-dev`, then re-run `install_offline.sh`. The **web demo** (`./offline/run_all.sh`) does not need PyAudio.

## Scripts summary

| Script | Run where | Purpose |
|--------|-----------|--------|
| `offline/download_bundle.sh` | Online | Download wheels, Whisper model, GGUF, npm into `offline/vendor/` |
| `offline/install_offline.sh` | Airgapped | Install pip from wheels and prepare npm (no network) |
| `offline/run_all.sh` | Airgapped | Start LLM server + backend + frontend |

Config file: **`offline/offline_config.env`** (copy from `offline_config.env.example`). Used by `run_all.sh` for model paths and ports.
