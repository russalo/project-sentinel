"""Load an engine.WorldContext from the on-disk data/ tree.

Per ADR 0001, data/state/*.json is canonical. The backend reads these
files directly. At v1.0 scale (hundreds of entities, not millions),
reading the relevant JSON files per turn is cheap.

This module is the only place in the backend that shells out the
data/ tree. Route handlers call ``load_world_context(data_dir,
session_id, recent_turns)`` and get back a plain ``engine.WorldContext``
dataclass ready to hand to the DM agent.

Missing files are handled gracefully: a freshly-created world has
nothing in ``data/state/core/entities/`` yet, and the first turn
needs to see an empty but-valid context, not a crash.
"""

import json
from pathlib import Path
from typing import Any

import engine

# Path layout mirrors what engine.agents.fact_extractor writes:
# data/state/core/<category>/<slug>.json
_CORE = Path("state/core")
_WORLD_FILE = _CORE / "world" / "state.json"
_ENTITIES_DIR = _CORE / "entities"
_LOCATIONS_DIR = _CORE / "locations"
_FACTIONS_DIR = _CORE / "factions"
_ITEMS_DIR = _CORE / "items"


def _read_json_or_none(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_json_dir(path: Path) -> list[dict[str, Any]]:
    """Return all top-level .json files in a directory as a list of dicts.

    Non-existent directory, unreadable files, and non-dict JSON contents
    all resolve to "skip silently" rather than raising — world context
    loading must never be a fatal error, even against a partial or
    corrupted data tree.
    """
    if not path.exists() or not path.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        parsed = _read_json_or_none(file)
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def load_world_context(
    data_dir: Path,
    session_id: str | None = None,
    recent_turns: list[dict[str, Any]] | None = None,
) -> engine.WorldContext:
    """Build an engine.WorldContext snapshot from data/ on disk.

    Parameters
    ----------
    data_dir
        The repo's ``data/`` directory. Resolves to
        ``<data_dir>/state/core/<...>``.
    session_id
        Unused today, but passed through so this signature is stable
        if future world state becomes session-scoped.
    recent_turns
        List of recent turn dicts (``{playerAction, narrative}``) to
        feed the DM's "RECENT TURNS" prompt block. Callers load these
        from the session file.

    Returns
    -------
    engine.WorldContext
        A plain dataclass ready to pass into the DM agent. Empty
        collections and sensible defaults on a fresh tree.
    """
    core = data_dir / _CORE

    # `or {}` catches missing/empty; the isinstance guard additionally
    # catches a well-formed-but-non-dict state.json (a JSON list, string,
    # or number) so the `.get(...)` calls below can't AttributeError on a
    # corrupted/hand-edited world file. (gemini-high on PR #144.)
    _world_loaded = _read_json_or_none(data_dir / _WORLD_FILE)
    world_raw = _world_loaded if isinstance(_world_loaded, dict) else {}

    characters = _read_json_dir(core / "entities")
    locations = _read_json_dir(core / "locations")
    factions = _read_json_dir(core / "factions")
    items = _read_json_dir(core / "items")

    # ADR-0005 / RFC-0005: a world's active module set lives in its
    # state.json ``modules`` map. Pass it through verbatim; the engine
    # lazy-defaults to the base-only set when it's absent (legacy worlds
    # created before the field existed), so a missing map is not written
    # back — it simply resolves to the core default at prompt-assembly time.
    modules_raw = world_raw.get("modules")
    modules = modules_raw if isinstance(modules_raw, dict) else None

    return engine.WorldContext(
        world_name=world_raw.get("worldName", "Unknown Realm"),
        current_era=world_raw.get("currentEra", "The Age of Fracture"),
        current_location=world_raw.get("currentLocation", "Nowhere"),
        weather=world_raw.get("weather", "Calm"),
        time_of_day=world_raw.get("timeOfDay", "Day"),
        tension=int(world_raw.get("tension", 0) or 0),
        day=int(world_raw.get("day", 1) or 1),
        characters=characters,
        locations=locations,
        factions=factions,
        items=items,
        recent_turns=recent_turns or [],
        modules=modules,
    )
