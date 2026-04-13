"""Tests for POST /api/session/new.

Every outbound engine call is stubbed via the ``app`` fixture in
conftest.py — no real OpenAI, no real fs-manager. The tests verify:

- response shape matches the frontend's contract (camelCase,
  `sessionId`, `turns[0].narrative`)
- the intro flow dispatches the expected sequence to fs-manager
- error modes return usable HTTP status codes
"""

import json
import re


def _opening_response() -> str:
    return (
        "You step from the trackless wastes into the Crossroads Tavern. "
        "Old Maren watches from a corner; firelight flickers.\n"
        "<world_update>\n"
        '{'
        '"world": {"currentLocation": "Crossroads Tavern", "tension": 2},'
        '"characters": [{"name": "Old Maren", "action": "upsert", "role": "npc", "status": "alive"}],'
        '"locations": [{"name": "Crossroads Tavern", "action": "upsert", "type": "tavern"}]'
        '}\n'
        "</world_update>"
    )


def test_new_session_happy_path_returns_session_with_opening_turn(
    client, fake_openai, fake_dispatch_log
):
    fake_openai.chat.completions.set_blocking_response(_opening_response())

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "The Shattered Expanse",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Wanderer",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Frontend contract: sessionId + turns[0].narrative are the only
    # fields WorldCreation.jsx reads.
    assert "sessionId" in data
    assert data["worldName"] == "The Shattered Expanse"
    assert len(data["turns"]) == 1

    turn_zero = data["turns"][0]
    assert turn_zero["turnNumber"] == 0
    assert "Crossroads Tavern" in turn_zero["narrative"]
    # The <world_update> block must be stripped from the narrative the
    # player sees — it's internal state, not story beat.
    assert "<world_update>" not in turn_zero["narrative"]
    # The raw DM hint block goes to the frontend as worldUpdates
    assert "world" in turn_zero["worldUpdates"]
    assert turn_zero["worldUpdates"]["world"]["currentLocation"] == "Crossroads Tavern"


def test_new_session_dispatches_initial_world_state_to_fs_manager(
    client, fake_openai, fake_dispatch_log
):
    fake_openai.chat.completions.set_blocking_response(_opening_response())

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "P",
            "playerCharacterClass": "C",
        },
    )
    assert response.status_code == 200

    # Two dispatches: (1) the Fact-Extractor payload for the world/
    # entity state, (2) the session-metadata write.
    assert len(fake_dispatch_log) == 2

    fact_payload = fake_dispatch_log[0]["payload"]
    targets = {u["target_file"] for u in fact_payload["updates"]}
    assert "data/state/core/world/state.json" in targets
    assert "data/state/core/entities/old_maren.json" in targets
    assert "data/state/core/locations/crossroads_tavern.json" in targets

    session_payload = fake_dispatch_log[1]["payload"]
    assert len(session_payload["updates"]) == 1
    session_target = session_payload["updates"][0]["target_file"]
    assert session_target.startswith("data/state/core/sessions/")
    assert session_target.endswith(".json")


def test_new_session_with_empty_dm_block_still_creates_session(
    client, fake_openai, fake_dispatch_log
):
    """If the LLM forgot to emit a <world_update> block, the session
    should still be created — the narrative has value on its own.
    Only the session-metadata dispatch happens; the Fact-Extractor
    returns payload=None and there's no world-state dispatch."""
    fake_openai.chat.completions.set_blocking_response(
        "The tavern is silent. Nothing stirs."
    )

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Empty",
            "playerCharacterName": "Ghost",
            "playerCharacterClass": "Wraith",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["turns"][0]["narrative"].startswith("The tavern is silent.")

    # Only one dispatch happened: the session metadata write.
    assert len(fake_dispatch_log) == 1
    assert "sessions" in fake_dispatch_log[0]["payload"]["updates"][0]["target_file"]


def test_new_session_uses_defaults_when_fields_omitted(client, fake_openai):
    fake_openai.chat.completions.set_blocking_response(
        "Default world, default hero. <world_update>{}</world_update>"
    )

    response = client.post("/api/session/new", json={})
    assert response.status_code == 200
    data = response.json()
    # NewSessionRequest defaults
    assert data["worldName"] == "The Shattered Realm"
