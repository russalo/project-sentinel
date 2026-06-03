"""Tests for GET /api/world/{world_id} — the Slice 4 hydration endpoint.

These run in legacy/shared mode (test_settings has worlds_root=None), so
find_world_session filters the shared sessions dir by the stored world_id.
"""

from __future__ import annotations

import json

WORLD_ID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _seed_session(data_dir, *, session_id=SESSION_ID, world_id=WORLD_ID, turns=None):
    sessions = data_dir / "state" / "core" / "sessions"
    payload = {
        "session_id": session_id,
        "world_id": world_id,
        "world_name": "Saltmarsh",
        "dm_persona_name": "Oracle",
        "persona_id": "oracle",
        "mood": "ominous",
        "player_character_name": "Russalo",
        "player_character_class": "Warden",
        "started_at": "2026-06-03T00:00:00+00:00",
        "active": True,
        "turns": turns
        if turns is not None
        else [
            {"turn_number": 0, "player_action": "[start]", "narrative": "You arrive."},
            {"turn_number": 1, "player_action": "look", "narrative": "Fog rolls in."},
        ],
    }
    (sessions / f"{session_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_get_world_returns_session_for_hydration(client, tmp_data_dir):
    _seed_session(tmp_data_dir)
    # Seed a canonical entity so worldState rehydration has something to return.
    entities = tmp_data_dir / "state" / "core" / "entities"
    (entities / "kael.json").write_text(
        json.dumps({"name": "Kael", "status": "alive"}), encoding="utf-8"
    )
    r = client.get(f"/api/world/{WORLD_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["worldId"] == WORLD_ID
    assert body["sessionId"] == SESSION_ID
    assert body["worldName"] == "Saltmarsh"
    assert body["persona"] == "Oracle"
    assert body["personaId"] == "oracle"
    assert body["mood"] == "ominous"
    assert body["character"] == "Russalo"
    assert body["characterClass"] == "Warden"
    assert len(body["turns"]) == 2
    assert body["turns"][1]["narrative"] == "Fog rolls in."
    # World-state block for panel rehydration.
    names = {c["name"] for c in body["worldState"]["characters"]}
    assert "Kael" in names


def test_get_world_404_when_no_session_for_world(client, tmp_data_dir):
    # A session exists, but for a DIFFERENT world.
    _seed_session(tmp_data_dir, world_id="00000000-0000-0000-0000-000000000000")
    assert client.get(f"/api/world/{WORLD_ID}").status_code == 404


def test_get_world_404_when_empty(client, tmp_data_dir):
    assert client.get(f"/api/world/{WORLD_ID}").status_code == 404


def test_get_world_404_on_non_uuid(client, tmp_data_dir):
    # find_world_session → resolve_world_data_dir raises ValueError in per-world
    # mode; in legacy mode a non-UUID simply matches nothing. Either way: 404,
    # never a 500 or a traversal.
    assert client.get("/api/world/not-a-uuid").status_code == 404


def test_get_world_picks_most_recent_session(client, tmp_data_dir):
    """When a world has multiple sessions, hydrate the most-recently-modified."""
    import os
    import time

    old = "aaaaaaaa-0000-0000-0000-000000000000"
    new = "bbbbbbbb-0000-0000-0000-000000000000"
    _seed_session(tmp_data_dir, session_id=old)
    _seed_session(tmp_data_dir, session_id=new)
    sessions = tmp_data_dir / "state" / "core" / "sessions"
    # Make `new` clearly newer regardless of write order / fs granularity.
    past = time.time() - 100
    os.utime(sessions / f"{old}.json", (past, past))

    body = client.get(f"/api/world/{WORLD_ID}").json()
    assert body["sessionId"] == new
