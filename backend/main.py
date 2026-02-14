"""
FastAPI backend for the Voice-Controlled Game Map web demo.
Holds the GameMap state and exposes REST endpoints for the frontend and orchestrator.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow importing game_state from project root when running: uvicorn backend.main:app
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from game_state import GameMap, LOCATIONS

app = FastAPI(title="Voice Game Map API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared state (orchestrator can run in another process and POST here)
game: GameMap = GameMap()
# Seed one knight for demo (reset restores this)
game.add_knight("Sir Roland", "Castle")


def _coords(e: dict) -> tuple[int, int]:
    """Get (x, y) from entity; fallback to resolving location name."""
    if "coordinates" in e and e["coordinates"]:
        c = e["coordinates"]
        return (c[0], c[1]) if isinstance(c, (list, tuple)) else (c.get("x", 0), c.get("y", 0))
    loc = e.get("location") or ""
    return LOCATIONS.get(loc, (0, 0))


def _state_for_api() -> dict:
    """Build API state with (x, y) on every entity for the frontend grid."""
    snap = game.snapshot()
    # snapshot["locations"] is a list of location names; resolve to (x,y) from LOCATIONS
    location_names = snap.get("locations", [])
    locations = [{"name": n, "x": LOCATIONS.get(n, (0, 0))[0], "y": LOCATIONS.get(n, (0, 0))[1]} for n in location_names]
    if not locations:
        locations = [{"name": n, "x": xy[0], "y": xy[1]} for n, xy in LOCATIONS.items()]

    def with_xy(entities: list, key: str = "coordinates"):
        out = []
        for e in entities:
            x, y = _coords(e)
            ent = dict(e)
            if key in ent:
                del ent[key]
            ent["x"] = x
            ent["y"] = y
            out.append(ent)
        return out

    knights = with_xy(snap.get("knights", []))
    dragon_spots = with_xy(snap.get("dragon_spots", []))
    targets = with_xy(snap.get("targets", []))

    return {
        "grid": {"width": 55, "height": 30},
        "locations": locations if locations else [{"name": n, "x": xy[0], "y": xy[1]} for n, xy in LOCATIONS.items()],
        "knights": knights,
        "dragon_spots": dragon_spots,
        "targets": targets,
    }


# ---------- Request bodies ----------
class MoveKnightBody(BaseModel):
    to_location_name: str
    knight_name: str | None = None


class CreateDragonSpotBody(BaseModel):
    location_name: str
    dragon_type: str


class CreateTargetBody(BaseModel):
    location_name: str | None = None
    linked_dragon_spot_id: str | None = None


class AttackTargetBody(BaseModel):
    target_id: str
    attack_method: str = Field(..., pattern="^(knight|artillery)$")


class IdBody(BaseModel):
    id: str


class ChatBody(BaseModel):
    user_text: str


def _execute_tool(name: str, arguments: dict) -> str:
    """Run the corresponding GameMap method; return result message."""
    try:
        if name == "move_knight":
            return game.move_knight(
                to_location_name=arguments["to_location_name"],
                knight_name=arguments.get("knight_name"),
            )
        if name == "create_dragon_spot":
            return game.create_dragon_spot(
                location_name=arguments["location_name"],
                dragon_type=arguments["dragon_type"],
            )
        if name == "create_target":
            return game.create_target(
                location_name=arguments.get("location_name"),
                linked_dragon_spot_id=arguments.get("linked_dragon_spot_id"),
            )
        if name == "attack_target":
            return game.attack_target(
                target_id=arguments["target_id"],
                attack_method=arguments["attack_method"],
            )
        if name == "delete_target":
            return game.delete_target(target_id=arguments["target_id"])
        if name == "delete_dragon_spot":
            return game.delete_dragon_spot(dragon_spot_id=arguments["dragon_spot_id"])
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


# ---------- Endpoints ----------
@app.get("/state")
def get_state():
    return _state_for_api()


@app.post("/move_knight")
def move_knight(body: MoveKnightBody):
    msg = game.move_knight(to_location_name=body.to_location_name, knight_name=body.knight_name)
    return {"message": msg}


@app.post("/add_knight")
def add_knight(location_name: str, name: str = "Knight"):
    msg = game.add_knight(name=name, location_name=location_name)
    return {"message": msg}


@app.post("/delete_knight")
def delete_knight(body: IdBody):
    msg = game.delete_knight(body.id)
    return {"message": msg}


@app.post("/create_dragon_spot")
def create_dragon_spot(body: CreateDragonSpotBody):
    msg = game.create_dragon_spot(location_name=body.location_name, dragon_type=body.dragon_type)
    return {"message": msg}


@app.post("/create_target")
def create_target(body: CreateTargetBody):
    msg = game.create_target(
        location_name=body.location_name,
        linked_dragon_spot_id=body.linked_dragon_spot_id,
    )
    return {"message": msg}


@app.post("/attack_target")
def attack_target(body: AttackTargetBody):
    msg = game.attack_target(target_id=body.target_id, attack_method=body.attack_method)
    return {"message": msg}


@app.post("/delete_target")
def delete_target(body: IdBody):
    msg = game.delete_target(body.id)
    return {"message": msg}


@app.post("/delete_dragon_spot")
def delete_dragon_spot(body: IdBody):
    msg = game.delete_dragon_spot(body.id)
    return {"message": msg}


@app.post("/reset")
def reset_session():
    """Reset game to initial state: one knight at Castle, no targets/dragons."""
    global game
    game = GameMap()
    game.add_knight("Sir Roland", "Castle")
    return {"message": "Session reset."}


@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Accept an audio file (e.g. webm/wav); return transcribed text. Needs 16kHz mono for best results."""
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    upload_size = len(contents)
    if not contents:
        return {"text": ""}
    suffix = Path(file.filename or "audio").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", tmp_path,
                "-ar", "16000", "-ac", "1", "-f", "s16le",
                "pipe:1",
            ],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"ffmpeg failed: {proc.stderr.decode(errors='replace')[:200]}")
        raw = proc.stdout
        from audio_listener import transcribe_audio_bytes
        text = transcribe_audio_bytes(raw)
        return {"text": text or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.post("/chat")
async def chat(body: ChatBody):
    """Send user text to LLM with tools; execute tool calls and return response."""
    from llm_interface import (
        chat_with_tools,
        create_client,
        format_state_for_llm,
        SYSTEM_PROMPT,
    )
    import os
    base_url = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    model = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-3b-instruct")
    client = create_client(base_url=base_url)
    state_context = format_state_for_llm(game.snapshot())
    try:
        response = chat_with_tools(
            client=client,
            user_text=body.user_text,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            state_context=state_context,
        )
    except Exception as e:
        return {"content": "", "tool_results": [], "error": str(e)}
    msg = response.choices[0].message if response.choices else None
    if not msg:
        return {"content": "", "tool_results": []}
    tool_results = []
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.function.name if hasattr(tc.function, "name") else tc.get("function", {}).get("name")
        raw_args = tc.function.arguments if hasattr(tc.function, "arguments") else tc.get("function", {}).get("arguments", "{}")
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {}
        result = _execute_tool(name, args)
        tool_results.append({"tool": name, "arguments": args, "result": result})
    content = getattr(msg, "content", None) or ""
    return {"content": content.strip(), "tool_results": tool_results}
