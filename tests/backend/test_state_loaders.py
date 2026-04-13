"""Tests for backend/state/world_context.py and backend/state/sessions.py.

These are the read-side primitives the route handlers use. Both must
handle missing files, empty directories, and malformed JSON gracefully
(no crashes, sensible defaults).
"""

import json
from pathlib import Path

from backend.state.sessions import (
    Session,
    read_session,
    session_file_path,
)
from backend.state.world_context import load_world_context


def test_load_world_context_on_empty_tree_returns_defaults(tmp_data_dir):
    ctx = load_world_context(tmp_data_dir)
    assert ctx.world_name == "Unknown Realm"
    assert ctx.characters == []
    assert ctx.locations == []
    assert ctx.factions == []
    assert ctx.items == []
    assert ctx.recent_turns == []


def test_load_world_context_reads_world_and_collections(tmp_data_dir: Path):
    core = tmp_data_dir / "state" / "core"
    (core / "world" / "state.json").write_text(
        json.dumps(
            {
                "worldName": "Test",
                "currentLocation": "Plaza",
                "weather": "Rain",
                "timeOfDay": "Dusk",
                "tension": 5,
            }
        )
    )
    (core / "entities" / "kael.json").write_text(
        json.dumps({"name": "Kael", "role": "npc", "status": "alive"})
    )
    (core / "entities" / "mira.json").write_text(
        json.dumps({"name": "Mira", "role": "ally", "status": "alive"})
    )
    (core / "locations" / "plaza.json").write_text(
        json.dumps({"name": "Plaza", "type": "square"})
    )
    (core / "factions" / "grey_pact.json").write_text(
        json.dumps({"name": "Grey Pact", "playerRelation": -3})
    )

    ctx = load_world_context(
        tmp_data_dir,
        recent_turns=[{"playerAction": "enter plaza", "narrative": "Rain pours."}],
    )
    assert ctx.world_name == "Test"
    assert ctx.current_location == "Plaza"
    assert ctx.weather == "Rain"
    assert ctx.tension == 5
    assert len(ctx.characters) == 2
    names = {c["name"] for c in ctx.characters}
    assert names == {"Kael", "Mira"}
    assert ctx.locations[0]["name"] == "Plaza"
    assert ctx.factions[0]["name"] == "Grey Pact"
    assert ctx.recent_turns[0]["playerAction"] == "enter plaza"


def test_load_world_context_skips_malformed_json_files(tmp_data_dir: Path):
    core = tmp_data_dir / "state" / "core"
    (core / "entities" / "good.json").write_text(
        json.dumps({"name": "Good"})
    )
    (core / "entities" / "bad.json").write_text("{not valid json")
    (core / "entities" / "wrong_shape.json").write_text(
        json.dumps(["not", "an", "object"])
    )

    ctx = load_world_context(tmp_data_dir)
    names = {c.get("name") for c in ctx.characters}
    # Only the good file is loaded; the bad ones are silently skipped.
    assert names == {"Good"}


def test_read_session_returns_none_when_missing(tmp_data_dir):
    assert read_session(tmp_data_dir, "does-not-exist") is None


def test_read_session_loads_from_disk(tmp_data_dir: Path):
    session_id = "abc-123"
    sessions_dir = tmp_data_dir / "state" / "core" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_name": "Loaded",
                "started_at": "2026-04-13T00:00:00Z",
                "turns": [{"turn_number": 0, "player_action": "start"}],
                "active": True,
            }
        )
    )

    s = read_session(tmp_data_dir, session_id)
    assert s is not None
    assert isinstance(s, Session)
    assert s.world_name == "Loaded"
    assert s.active is True
    assert len(s.turns) == 1


def test_read_session_treats_non_dict_root_as_missing(tmp_data_dir: Path):
    sessions_dir = tmp_data_dir / "state" / "core" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "weird.json").write_text(json.dumps([1, 2, 3]))
    assert read_session(tmp_data_dir, "weird") is None


def test_session_file_path_roundtrip(tmp_data_dir: Path):
    p = session_file_path(tmp_data_dir, "xyz")
    assert p == tmp_data_dir / "state" / "core" / "sessions" / "xyz.json"
