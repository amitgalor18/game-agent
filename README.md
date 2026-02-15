# Voice-Controlled Game Map

Python demo for a voice-controlled game map on edge hardware (6GB VRAM laptop, mobile later). Voice → ASR (faster-whisper) → local LLM (LM Studio) with tool calls → persistent game state.

## Setup

- **Python 3.10+**
- **LM Studio** running with a model that supports tool/function calling (e.g. `qwen2.5-3b-instruct`) at `http://localhost:1234/v1`.

```bash
pip install -r requirements.txt
```

## Run

1. Start LM Studio and load the model; ensure the server is listening on port 1234.
2. Run the main loop:

```bash
python main.py
```

Optional env vars:

- `LM_STUDIO_BASE_URL` — default `http://localhost:1234/v1`
- `LM_STUDIO_MODEL` — default `qwen2.5-3b-instruct`
- `WHISPER_DEVICE` — `cpu` (default) or `cuda` / `auto` if you have working CUDA
- `WHISPER_MODEL` — ASR model: `large-v3-turbo` (default), or `distil-large-v3` / `base` / `small` for **faster transcription**

## Project layout

| File | Role |
|------|------|
| `game_state.py` | `GameMap`: locations, knights, dragon spots, targets; methods used as LLM tools. |
| `llm_interface.py` | OpenAI client for LM Studio; tool schema (location nicknames only). |
| `audio_listener.py` | `listen_and_transcribe()`: mic → VAD → faster-whisper. |
| `main.py` | Loop: listen → transcribe → LLM → execute tool → pretty-print state. |

## Commands (examples)

- “Move the knight to North Ridge”
- “Create a dragon spot at River Crossing, type fire”
- “Create a target at Castle”
- “Attack target target-xyz with knight”
- “Delete the target target-abc”

Locations are fixed nicknames (e.g. North Ridge, Castle, River Crossing); the LLM uses these strings and the state machine resolves coordinates.

## Transcription speed

If transcription feels slow (e.g. on CPU):

- Set **`WHISPER_MODEL=distil-large-v3`** for a faster, slightly less accurate model.
- The app uses **int8** on CPU and **beam_size=1** by default for speed. Quality is usually fine for short commands.

## LLM and current state

The current game state (knights, dragon spots, targets with their **ids** and locations) is sent to the LLM with every request. The model is instructed to use those exact ids (e.g. for “create target for blue dragon” it should pick the dragon spot id from the state, e.g. at Mountain Pass). If it still invents ids or locations, try a larger or better-instruct model in LM Studio (e.g. 7B+ or a model known for good tool use).

---

## Web demo (FastAPI + React)

A visual map runs in the browser. The backend holds the game state and exposes REST endpoints; the frontend polls and lets you click to spawn/delete entities.

### Run the API

From the project root:

```bash
pip install -r requirements.txt   # includes fastapi, uvicorn
python main.py --api
```

API: `http://localhost:8000`. Endpoints: `GET /state`, `POST /move_knight`, `POST /add_knight`, `POST /create_target`, `POST /attack_target`, `POST /delete_target`, `POST /delete_knight`, `POST /delete_dragon_spot`, etc.

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Put assets in `frontend/public/assets/`: `map.png`, `knight.png`, `target.png`, `hitspark.gif`, and optionally `dragon.png`.

### Layout

| Path | Role |
|------|------|
| `backend/main.py` | FastAPI app; single `GameMap` in memory; CORS for dev. |
| `frontend/` | Vite + React + Tailwind + Framer Motion; 55×30 grid overlay, entities by (x,y), context menus, poll every 500ms. |

Voice/orchestrator: run `python main.py` (no `--api`) in another terminal for the PTT UI. To have voice control update the web map, the orchestrator must call the API (e.g. `POST /move_knight`) instead of a local `GameMap`.

---

## Offline / airgapped run

To run the demo on a machine **without internet**, use the offline bundle: all models (Whisper + GGUF), Python wheels, and npm dependencies are downloaded into one folder, then copied to the airgapped PC.

1. **On an online machine:** run `./offline/download_bundle.sh` (downloads everything into `offline/vendor/`).
2. Copy the full project (including `offline/vendor/` and `frontend/node_modules`) to the airgapped PC.
3. **On the airgapped PC:** run `./offline/install_offline.sh`, then `./offline/run_all.sh`.

The LLM runs via **llama-cpp-python** (OpenAI-compatible server) using the bundled GGUF. See **`offline/README.md`** and **`offline/CONFIG.md`** for details and for **where to change the LLM or Whisper model**.
