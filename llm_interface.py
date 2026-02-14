"""
LLM Interface — The Brain.
OpenAI-compatible client for local LM Studio; tool definitions for game actions.
Keep tool schemas minimal and clear for small models (<3B). Use location NICKNAMES only, not coordinates.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

# LM Studio default endpoint
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen2.5-3b-instruct"

# Location nicknames the model must use (strings only). game_state resolves to coordinates.
LOCATION_NAMES = [
    "North Ridge",
    "Castle",
    "River Crossing",
    "Forest Edge",
    "Mountain Pass",
    "Village",
    "Tower",
    "Bridge",
]


def _tools_schema() -> list[dict[str, Any]]:
    """
    Minimal tool definitions for a small model.
    All location arguments are strings (place names). No coordinates.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "move_knight",
                "description": "Move a knight to a location. Use the exact location name from the map.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to_location_name": {
                            "type": "string",
                            "description": "Location name, e.g. North Ridge, Castle, River Crossing",
                            "enum": LOCATION_NAMES,
                        },
                        "knight_name": {
                            "type": "string",
                            "description": "Optional. Which knight to move. If omitted, move the first knight.",
                        },
                    },
                    "required": ["to_location_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_knight",
                "description": "Add a knight to the map. Use the exact location name from the map.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the knight to add.",
                        },
                        "location_name": {
                            "type": "string",
                            "description": "Location name to add the knight to. If omitted, add the knight to the castle.",
                            "enum": LOCATION_NAMES,
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        
        {
            "type": "function",
            "function": {
                "name": "create_dragon_spot",
                "description": "Add a dragon spot at a location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_name": {
                            "type": "string",
                            "description": "Location name",
                            "enum": LOCATION_NAMES,
                        },
                        "dragon_type": {
                            "type": "string",
                            "description": "Type of dragon, e.g. fire, ice",
                        },
                    },
                    "required": ["location_name", "dragon_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_target",
                "description": "Create a target. Optionally link it to a dragon spot (then location comes from that spot).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_name": {
                            "type": "string",
                            "description": "Location name. Omit if linking to a dragon spot.",
                            "enum": LOCATION_NAMES,
                        },
                        "linked_dragon_spot_id": {
                            "type": "string",
                            "description": "Optional. Dragon spot id to attach target to; target gets that location.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attack_target",
                "description": "Neutralize a target (or the target linked to a dragon). Pass either a target id or a dragon_spot id; if you pass a dragon spot id, the target linked to that dragon is attacked. Knight attack only works when a knight is at the same location as the target.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "Target id (e.g. target-abc123) OR dragon_spot id if user said 'attack the dragon' (e.g. dragon-xyz).",
                        },
                        "attack_method": {
                            "type": "string",
                            "description": "knight = only valid if a knight is at the target's location; otherwise use artillery.",
                            "enum": ["knight", "artillery"],
                        },
                    },
                    "required": ["target_id", "attack_method"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_target",
                "description": "Remove a target by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string", "description": "Target id to remove"},
                    },
                    "required": ["target_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_dragon_spot",
                "description": "Remove a dragon spot by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dragon_spot_id": {"type": "string", "description": "Dragon spot id to remove"},
                    },
                    "required": ["dragon_spot_id"],
                },
            },
        },
    ]


def create_client(base_url: str = DEFAULT_BASE_URL, api_key: str = "lm-studio") -> OpenAI:
    """Create OpenAI client pointing at LM Studio."""
    return OpenAI(base_url=base_url, api_key=api_key)


def get_tools() -> list[dict[str, Any]]:
    """Return the tools list for chat completion."""
    return _tools_schema()


def chat_with_tools(
    client: OpenAI,
    user_text: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
    state_context: str | None = None,
) -> Any:
    """
    Send user message with tools. Returns the completion object.
    If state_context is provided, it is prepended to the user message so the model
    sees current knights/dragon spots/targets and their ids—use exact ids from this list.
    """
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if state_context:
        user_content = f"Current game state (use these exact ids when referring to entities):\n{state_context}\n\nUser said: {user_text}"
    else:
        user_content = user_text
    messages.append({"role": "user", "content": user_content})

    return client.chat.completions.create(
        model=model,
        messages=messages,
        tools=get_tools(),
        tool_choice="auto",
    )


SYSTEM_PROMPT = """You are a game assistant for a voice-controlled map. The user speaks commands in natural language.

You must respond by calling exactly one of the available tools with the correct arguments.
You will be given the current game state with entity ids. You MUST use those exact ids—never invent or guess ids.
- move_knight(to_location_name, knight_name optional): use a location name from the list (North Ridge, Castle, River Crossing, Forest Edge, Mountain Pass, Village, Tower, Bridge).
- create_dragon_spot(location_name, dragon_type)
- create_target(location_name optional, linked_dragon_spot_id optional): to link to a dragon, use its id from the state; then omit location_name (target gets that spot's location).
- attack_target(target_id, attack_method): target_id can be a target id OR a dragon_spot id (e.g. when user says "attack the dragon" use the dragon spot id from the state). If attack_method is "knight", only call when a knight is at the same location as the target (otherwise use "artillery" or ask to move the knight first). Attack with knight can also hint at the desired target when no description is provided.
- delete_target(target_id)
- delete_dragon_spot(dragon_spot_id)

When the user says "target for blue dragon" or similar, find the dragon spot with that type in the state and use its id for linked_dragon_spot_id. When they say "attack the dragon" or "attack the blue dragon", use the dragon spot id as target_id (the game will resolve to the linked target).
Keep responses short. Prefer tool calls over long text."""


def format_state_for_llm(snapshot: dict) -> str:
    """Format game snapshot for LLM context: compact lines with ids so model can reference them."""
    lines = []
    for k in snapshot.get("knights", []):
        lines.append(f"Knight: id={k['id']} name={k['name']} location={k['location']}")
    if not snapshot.get("knights"):
        lines.append("Knights: (none)")
    for d in snapshot.get("dragon_spots", []):
        lines.append(f"Dragon spot: id={d['id']} location={d['location']} type={d['type']} status={d['status']}")
    if not snapshot.get("dragon_spots"):
        lines.append("Dragon spots: (none)")
    for t in snapshot.get("targets", []):
        link = f" linked_dragon_spot_id={t['linked_dragon_spot_id']}" if t.get("linked_dragon_spot_id") else ""
        lines.append(f"Target: id={t['id']} location={t['location']}{link} status={t['status']}")
    if not snapshot.get("targets"):
        lines.append("Targets: (none)")
    return "\n".join(lines)
