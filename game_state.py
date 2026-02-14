"""
Game State — The State Machine.
Manages locations, knights, dragon spots, and targets for the voice-controlled map.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Locations (nickname -> (x, y)). Used by LLM as string arguments.
# ---------------------------------------------------------------------------
LOCATIONS: dict[str, tuple[int, int]] = {
    "North Ridge": (30, 8),
    "Castle": (30, 16),
    "River Crossing": (42, 24),
    "Forest Edge": (8, 14),
    "Mountain Pass": (52, 8),
    "Village": (50, 26),
    "Tower": (14, 26),
    "Bridge": (42, 16),
}


class AttackMethod(str, Enum):
    KNIGHT = "knight"
    ARTILLERY = "artillery"


# ---------------------------------------------------------------------------
# Entity records (plain dicts for JSON-friendly state).
# ---------------------------------------------------------------------------

def _make_knight(name: str, location_name: str) -> dict[str, Any]:
    coords = LOCATIONS.get(location_name, (0, 0))
    return {
        "id": f"knight-{uuid.uuid4().hex[:8]}",
        "name": name,
        "location": location_name,
        "coordinates": coords,
    }


def _make_dragon_spot(location_name: str, dragon_type: str) -> dict[str, Any]:
    coords = LOCATIONS.get(location_name, (0, 0))
    return {
        "id": f"dragon-{uuid.uuid4().hex[:8]}",
        "location": location_name,
        "coordinates": coords,
        "type": dragon_type,
        "status": "active",
    }


def _make_target(
    location_name: str | None,
    linked_dragon_spot_id: str | None,
) -> dict[str, Any]:
    return {
        "id": f"target-{uuid.uuid4().hex[:8]}",
        "location": location_name or "",
        "linked_dragon_spot_id": linked_dragon_spot_id,
        "status": "active",
    }


# ---------------------------------------------------------------------------
# GameMap — single source of truth for map state.
# ---------------------------------------------------------------------------


class GameMap:
    """
    Manages the persistent game state: locations, knights, dragon spots, targets.
    All location arguments are string nicknames (e.g. "North Ridge"); coordinates
    are resolved internally to reduce LLM hallucination.
    """

    def __init__(self) -> None:
        self._locations = dict(LOCATIONS)
        self._knights: list[dict[str, Any]] = []
        self._dragon_spots: list[dict[str, Any]] = []
        self._targets: list[dict[str, Any]] = []

    def _resolve_location(self, location_name: str) -> tuple[int, int]:
        for k, v in self._locations.items():
            if k.lower() == location_name.strip().lower():
                return v
        self._locations[location_name.strip()] = (0, 0)
        return (0, 0)

    def _canonical_location_name(self, location_name: str) -> str:
        """Return the canonical key from LOCATIONS for display/storage."""
        name = location_name.strip()
        for k in self._locations:
            if k.lower() == name.lower():
                return k
        return name

    # ---------- Knights ----------
    def move_knight(self, to_location_name: str, knight_name: str | None = None) -> str:
        """Move a knight to a named location. If knight_name is None, move the first knight."""
        if not self._knights:
            return "No knights on the map. Create a knight first."
        canonical = self._canonical_location_name(to_location_name)
        coords = self._resolve_location(to_location_name)
        if knight_name is not None:
            for k in self._knights:
                if k["name"].lower() == knight_name.lower():
                    k["location"] = canonical
                    k["coordinates"] = coords
                    return f"Moved knight '{k['name']}' to {canonical}."
            return f"No knight named '{knight_name}' found."
        self._knights[0]["location"] = canonical
        self._knights[0]["coordinates"] = coords
        return f"Moved knight '{self._knights[0]['name']}' to {canonical}."

    def add_knight(self, name: str, location_name: str = "Castle") -> str:
        """Add a knight at a location (convenience for initial setup)."""
        canonical = self._canonical_location_name(location_name)
        knight = _make_knight(name, canonical)
        knight["coordinates"] = self._resolve_location(location_name)
        self._knights.append(knight)
        return f"Added knight '{name}' at {canonical}."

    def delete_knight(self, knight_id: str) -> str:
        """Remove a knight by id."""
        for i, k in enumerate(self._knights):
            if k["id"] == knight_id:
                self._knights.pop(i)
                return f"Removed knight {knight_id}."
        return f"Knight {knight_id} not found."

    # ---------- Dragon spots ----------
    def create_dragon_spot(self, location_name: str, dragon_type: str) -> str:
        """Add a dragon spot at a named location."""
        canonical = self._canonical_location_name(location_name)
        spot = _make_dragon_spot(canonical, dragon_type)
        spot["coordinates"] = self._resolve_location(location_name)
        self._dragon_spots.append(spot)
        return f"Created dragon spot ({dragon_type}) at {location_name}."

    def delete_dragon_spot(self, dragon_spot_id: str) -> str:
        """Remove a dragon spot by id."""
        for i, d in enumerate(self._dragon_spots):
            if d["id"] == dragon_spot_id:
                self._dragon_spots.pop(i)
                return f"Removed dragon spot {dragon_spot_id}."
        return f"Dragon spot {dragon_spot_id} not found."

    # ---------- Targets ----------
    def create_target(
        self,
        location_name: str | None = None,
        linked_dragon_spot_id: str | None = None,
    ) -> str:
        """Create a target. If linked_dragon_spot_id is set, target inherits that spot's location."""
        if linked_dragon_spot_id:
            loc = None
            coords = (0, 0)
            for d in self._dragon_spots:
                if d["id"] == linked_dragon_spot_id:
                    loc = d["location"]
                    coords = d.get("coordinates", (0, 0))
                    break
            target = _make_target(loc, linked_dragon_spot_id)
            if loc:
                target["location"] = loc
                target["coordinates"] = coords
        else:
            canonical = self._canonical_location_name(location_name or "")
            target = _make_target(canonical or None, None)
            if location_name:
                target["location"] = canonical
                target["coordinates"] = self._resolve_location(location_name)
        self._targets.append(target)
        return f"Created target at {target['location'] or 'linked location'}."

    def _neutralize_target(self, t: dict[str, Any]) -> None:
        """Set target to neutralized and its linked dragon spot if any."""
        t["status"] = "neutralized"
        linked = t.get("linked_dragon_spot_id")
        if linked:
            for d in self._dragon_spots:
                if d["id"] == linked:
                    d["status"] = "neutralized"
                    break

    def _knight_at_location(self, location: str) -> bool:
        """True if any knight is at the given location."""
        return any(k["location"] == location for k in self._knights)

    def attack_target(self, target_id: str, attack_method: str) -> str:
        """
        Attack a target (or the target linked to a dragon spot).
        target_id can be a target id OR a dragon_spot id; if it's a dragon spot id,
        the target linked to that spot is attacked (and the dragon is neutralized too).
        attack_method: knight (only valid if a knight is at the target's location) or artillery.
        """
        try:
            method = AttackMethod(attack_method.lower())
        except ValueError:
            return f"Invalid attack_method: {attack_method}. Use 'knight' or 'artillery'."

        # Resolve target_id to the actual target(s) to neutralize
        resolved_targets: list[dict[str, Any]] = []
        dragon_spot_to_neutralize: dict[str, Any] | None = None

        for t in self._targets:
            if t["id"] == target_id:
                resolved_targets.append(t)
                break
        if not resolved_targets:
            # Maybe target_id is a dragon_spot id: find target(s) linked to it
            for d in self._dragon_spots:
                if d["id"] == target_id:
                    dragon_spot_to_neutralize = d
                    for t in self._targets:
                        if t.get("linked_dragon_spot_id") == target_id:
                            resolved_targets.append(t)
                    break

        if dragon_spot_to_neutralize is not None and not resolved_targets:
            # Dragon spot has no linked target; just neutralize the dragon
            dragon_spot_to_neutralize["status"] = "neutralized"
            return f"Dragon spot {target_id} neutralized ({method.value})."

        if not resolved_targets:
            return f"Target or dragon spot {target_id} not found."

        for t in resolved_targets:
            if method == AttackMethod.KNIGHT and not self._knight_at_location(t["location"]):
                return (
                    f"Cannot attack with knight: no knight at {t['location']}. "
                    "Move a knight there first or use artillery."
                )
            self._neutralize_target(t)
        return f"Target(s) neutralized ({method.value})."

    def delete_target(self, target_id: str) -> str:
        """Remove a target by id."""
        for i, t in enumerate(self._targets):
            if t["id"] == target_id:
                self._targets.pop(i)
                return f"Removed target {target_id}."
        return f"Target {target_id} not found."

    # ---------- Snapshot for display ----------
    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of current state (no methods)."""
        return {
            "locations": list(self._locations.keys()),
            "knights": [dict(k) for k in self._knights],
            "dragon_spots": [dict(d) for d in self._dragon_spots],
            "targets": [dict(t) for t in self._targets],
        }
