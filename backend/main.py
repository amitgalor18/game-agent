"""
FastAPI backend for the Voice-Controlled Game Map web demo.
Holds the GameMap state and exposes REST endpoints for the frontend and orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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


# Pixel noise range in grid units so icons at same location don't fully overlap
_PLACEMENT_NOISE = 1.2


def _placement_offset(entity_id: str) -> tuple[float, float]:
    """Stable offset per entity (from id hash) so the same entity always gets the same noise."""
    b = hashlib.md5(entity_id.encode()).digest()
    dx = (b[0] / 127.5 - 1.0) * _PLACEMENT_NOISE
    dy = (b[1] / 127.5 - 1.0) * _PLACEMENT_NOISE
    return (dx, dy)


def _state_for_api() -> dict:
    """Build API state with (x, y) on every entity for the frontend grid."""
    snap = game.snapshot()
    game_active = snap.get("game_active", False)
    turn_count = snap.get("turn_count", 0)
    trebuchet_cooldown = snap.get("trebuchet_cooldown", 0)
    trebuchet_available = snap.get("trebuchet_available", True)
    turn_logs = snap.get("turn_logs", [])
    # snapshot["locations"] is a list of location names; resolve to (x,y) from LOCATIONS
    location_names = snap.get("locations", [])
    locations = [{"name": n, "x": LOCATIONS.get(n, (0, 0))[0], "y": LOCATIONS.get(n, (0, 0))[1]} for n in location_names]
    if not locations:
        locations = [{"name": n, "x": xy[0], "y": xy[1]} for n, xy in LOCATIONS.items()]

    def with_xy(entities: list, key: str = "coordinates", add_noise: bool = True):
        out = []
        for e in entities:
            x, y = _coords(e)
            if add_noise:
                dx, dy = _placement_offset(e.get("id", ""))
                x, y = x + dx, y + dy
            ent = dict(e)
            if key in ent:
                del ent[key]
            ent["x"] = x
            ent["y"] = y
            out.append(ent)
        return out

    knights = with_xy(snap.get("knights", []), add_noise=True)
    dragon_spots = with_xy(snap.get("dragon_spots", []), add_noise=True)
    trebuchets = with_xy(snap.get("trebuchets", []), add_noise=True)
    # Dragon display position (with noise) so linked targets can match exactly
    dragon_display_by_id = {d["id"]: (d["x"], d["y"]) for d in dragon_spots}
    # Targets linked to a dragon: exact dragon *display* location (no noise); others: add noise
    targets_raw = snap.get("targets", [])
    targets = []
    for t in targets_raw:
        ent = dict(t)
        if "coordinates" in ent:
            del ent["coordinates"]
        linked_id = t.get("linked_dragon_spot_id")
        if linked_id and linked_id in dragon_display_by_id:
            x, y = dragon_display_by_id[linked_id]
            ent["x"] = x
            ent["y"] = y
        else:
            x, y = _coords(t)
            dx, dy = _placement_offset(t.get("id", ""))
            ent["x"] = x + dx
            ent["y"] = y + dy
        targets.append(ent)

    # One-shot effects for frontend (clear after sending)
    effect_knight_killed_at = getattr(game, "_effect_knight_killed_at", None)
    effect_dragon_killed_by_knight_at = getattr(game, "_effect_dragon_killed_by_knight_at", None)
    effect_dragon_killed_by_artillery_at = getattr(game, "_effect_dragon_killed_by_artillery_at", None)
    game._effect_knight_killed_at = None
    game._effect_dragon_killed_by_knight_at = None
    game._effect_dragon_killed_by_artillery_at = None

    return {
        "grid": {"width": 55, "height": 30},
        "locations": locations if locations else [{"name": n, "x": xy[0], "y": xy[1]} for n, xy in LOCATIONS.items()],
        "knights": knights,
        "dragon_spots": dragon_spots,
        "targets": targets,
        "trebuchets": trebuchets,
        "game_active": game_active,
        "turn_count": turn_count,
        "trebuchet_cooldown": trebuchet_cooldown,
        "trebuchet_available": trebuchet_available,
        "turn_logs": turn_logs,
        "effect_knight_killed_at": effect_knight_killed_at,
        "effect_dragon_killed_by_knight_at": effect_dragon_killed_by_knight_at,
        "effect_dragon_killed_by_artillery_at": effect_dragon_killed_by_artillery_at,
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


class SetGameActiveBody(BaseModel):
    game_active: bool


class CreateTrebuchetBody(BaseModel):
    location_name: str


class ChatBody(BaseModel):
    user_text: str


def _after_player_action() -> None:
    """Run enemy turn after a successful player action when simulation is active."""
    if game.game_active:
        game.process_enemy_turn()


def _execute_tool(name: str, arguments: dict) -> str:
    """Run the corresponding GameMap method; return result message."""
    try:
        result = None
        if name == "move_knight":
            result = game.move_knight(
                to_location_name=arguments["to_location_name"],
                knight_name=arguments.get("knight_name"),
            )
        elif name == "add_knight":
            result = game.add_knight(
                name=arguments.get("name", "Knight"),
                location_name=arguments.get("location_name", "Castle"),
            )
        elif name == "delete_knight":
            result = game.delete_knight(knight_id=arguments["knight_id"])
        elif name == "create_dragon_spot":
            result = game.create_dragon_spot(
                location_name=arguments["location_name"],
                dragon_type=arguments["dragon_type"],
            )
        elif name == "create_target":
            result = game.create_target(
                location_name=arguments.get("location_name"),
                linked_dragon_spot_id=arguments.get("linked_dragon_spot_id"),
            )
        elif name == "create_trebuchet":
            result = game.create_trebuchet(location_name=arguments["location_name"])
        elif name == "attack_target":
            result = game.attack_target(
                target_id=arguments["target_id"],
                attack_method=arguments["attack_method"],
            )
        elif name == "delete_target":
            result = game.delete_target(target_id=arguments["target_id"])
        elif name == "delete_dragon_spot":
            result = game.delete_dragon_spot(dragon_spot_id=arguments["dragon_spot_id"])
        else:
            return f"Unknown tool: {name}"
        # Log player action and run enemy turn only after a successful state-changing tool
        if result and not result.startswith("Error:") and not result.startswith("No ") and "not found" not in result and "Cannot " not in result:
            game.log_player_action(result)
            _after_player_action()
        return result
    except Exception as e:
        return f"Error: {e}"


# ---------- Endpoints ----------
@app.get("/state")
def get_state():
    return _state_for_api()


@app.post("/move_knight")
def move_knight(body: MoveKnightBody):
    msg = game.move_knight(to_location_name=body.to_location_name, knight_name=body.knight_name)
    if msg and "not found" not in msg and "No " not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/add_knight")
def add_knight(location_name: str, name: str = "Knight"):
    msg = game.add_knight(name=name, location_name=location_name)
    game.log_player_action(msg)
    _after_player_action()
    return {"message": msg}


@app.post("/delete_knight")
def delete_knight(body: IdBody):
    msg = game.delete_knight(body.id)
    if msg and "not found" not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/create_dragon_spot")
def create_dragon_spot(body: CreateDragonSpotBody):
    msg = game.create_dragon_spot(location_name=body.location_name, dragon_type=body.dragon_type)
    game.log_player_action(msg)
    _after_player_action()
    return {"message": msg}


@app.post("/create_target")
def create_target(body: CreateTargetBody):
    msg = game.create_target(
        location_name=body.location_name,
        linked_dragon_spot_id=body.linked_dragon_spot_id,
    )
    game.log_player_action(msg)
    _after_player_action()
    return {"message": msg}


@app.post("/create_trebuchet")
def create_trebuchet(body: CreateTrebuchetBody):
    msg = game.create_trebuchet(location_name=body.location_name)
    if msg and "Cannot " not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/attack_target")
def attack_target(body: AttackTargetBody):
    msg = game.attack_target(target_id=body.target_id, attack_method=body.attack_method)
    if msg and "not found" not in msg and "Cannot " not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/delete_target")
def delete_target(body: IdBody):
    msg = game.delete_target(body.id)
    if msg and "not found" not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/delete_dragon_spot")
def delete_dragon_spot(body: IdBody):
    msg = game.delete_dragon_spot(body.id)
    if msg and "not found" not in msg:
        game.log_player_action(msg)
        _after_player_action()
    return {"message": msg}


@app.post("/set_game_active")
def set_game_active(body: SetGameActiveBody):
    game.set_game_active(body.game_active)
    return {"message": "Game " + ("started" if body.game_active else "paused") + "."}


@app.post("/reset")
def reset_session():
    """Reset game to initial state: one knight at Castle, no targets/dragons."""
    global game
    game = GameMap()
    game.add_knight("Sir Roland", "Castle")
    return {"message": "Session reset."}


def _ffmpeg_required_message() -> str:
    return (
        "ffmpeg is required for voice transcription but was not found. "
        "Install it and ensure it is on PATH (e.g. on Linux/WSL: sudo apt install ffmpeg), "
        "or place ffmpeg in offline/vendor/ffmpeg/ (see offline/README.md)."
    )


def _resolve_ffmpeg() -> str | None:
    """Return path to ffmpeg: env FFMPEG_PATH, then system PATH, then bundled offline/vendor/ffmpeg.
    On Linux (e.g. WSL) we prefer system ffmpeg so it can read Linux temp paths; bundled .exe cannot."""
    if os.environ.get("FFMPEG_PATH"):
        p = Path(os.environ["FFMPEG_PATH"])
        if p.is_file():
            return str(p)
        for name in ("ffmpeg.exe", "ffmpeg"):
            if (p / name).is_file():
                return str(p / name)
        return None
    # Prefer system ffmpeg on non-Windows so temp file paths (e.g. /tmp/...) are readable by the binary
    if sys.platform != "win32":
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg
    project_root = Path(__file__).resolve().parent.parent
    bundled_dir = project_root / "offline" / "vendor" / "ffmpeg"
    # On Windows check .exe first; on Linux only use "ffmpeg" (Windows .exe cannot read Linux paths)
    names = ("ffmpeg.exe", "ffmpeg") if sys.platform == "win32" else ("ffmpeg",)
    for name in names:
        candidate = bundled_dir / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Accept an audio file (e.g. webm/wav); return transcribed text. Needs 16kHz mono for best results."""
    ffmpeg_cmd = _resolve_ffmpeg()
    if not ffmpeg_cmd:
        raise HTTPException(status_code=503, detail=_ffmpeg_required_message())
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    if not contents:
        return {"text": ""}
    suffix = Path(file.filename or "audio").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        proc = subprocess.run(
            [
                ffmpeg_cmd, "-y", "-i", tmp_path,
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
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=_ffmpeg_required_message())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# Tool names and param order for parsing "func(arg1, arg2)"-style fallback
_TOOL_PARAM_ORDER: dict[str, list[str]] = {
    "move_knight": ["to_location_name", "knight_name"],
    "add_knight": ["name", "location_name"],
    "create_dragon_spot": ["location_name", "dragon_type"],
    "create_target": ["location_name", "linked_dragon_spot_id"],
    "create_trebuchet": ["location_name"],
    "attack_target": ["target_id", "attack_method"],
    "delete_target": ["target_id"],
    "delete_dragon_spot": ["dragon_spot_id"],
}


def _parse_simple_args(s: str) -> list[str]:
    """Split by comma, strip quotes. Handles 'Village', \"North Ridge\", etc."""
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    for c in s.strip():
        if c in ("'", '"') and (in_quote is None or in_quote == c):
            in_quote = None if in_quote else c
        elif in_quote is None and c == ",":
            parts.append("".join(current).strip().strip("'\""))
            current = []
        else:
            current.append(c)
    if current:
        parts.append("".join(current).strip().strip("'\""))
    return parts


def _parse_tool_calls_from_content(content: str) -> list[tuple[str, dict]]:
    """Fallback: parse tool calls from model text. Handles:
    1) <tool_call>{"name": "...", "arguments": {...}}</tool_call>
    2) create_target(Village) or move_knight("North Ridge", "Sir Roland") style."""
    out: list[tuple[str, dict]] = []
    if not content:
        return out
    # 1) JSON inside <tool_call>...</tool_call>
    for m in re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL):
        raw = m.group(1).strip()
        if raw.startswith("{{") and raw.endswith("}}"):
            raw = raw[1:-1]
        try:
            obj = json.loads(raw)
            name = obj.get("name") or (obj.get("function") or {}).get("name")
            args = obj.get("arguments") or (obj.get("function") or {}).get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args) if args.strip() else {}
            if name:
                out.append((name, args))
        except (json.JSONDecodeError, TypeError):
            continue
    if out:
        return out
    # 2) func(arg1, arg2) style (e.g. create_target(Village))
    for name, param_names in _TOOL_PARAM_ORDER.items():
        # Match name( ... ) with any content inside parens
        pattern = re.escape(name) + r"\s*\(\s*([^)]*)\s*\)"
        for m in re.finditer(pattern, content, re.IGNORECASE):
            args_str = m.group(1).strip()
            if not args_str:
                continue
            parts = _parse_simple_args(args_str)
            args = {}
            for i, p in enumerate(param_names):
                if i < len(parts) and parts[i]:
                    args[p] = parts[i]
            if args:
                out.append((name, args))
    return out


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
    # Fallback: if no structured tool_calls, parse <tool_call>...</tool_call> from content
    content = getattr(msg, "content", None) or ""
    if not tool_results and content:
        for name, args in _parse_tool_calls_from_content(content):
            result = _execute_tool(name, args)
            tool_results.append({"tool": name, "arguments": args, "result": result})
    return {"content": content.strip(), "tool_results": tool_results}
