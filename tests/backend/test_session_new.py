"""Tests for POST /api/session/new.

Every outbound engine call is stubbed via the ``app`` fixture in
conftest.py — no real OpenAI, no real fs-manager. The tests verify:

- response shape matches the frontend's contract (camelCase,
  `sessionId`, `turns[0].narrative`)
- the intro flow dispatches the expected sequence to fs-manager
- error modes return usable HTTP status codes
"""


def _opening_response() -> str:
    return (
        "You step from the trackless wastes into the Crossroads Tavern. "
        "Old Maren watches from a corner; firelight flickers.\n"
        "<world_update>\n"
        "{"
        '"world": {"currentLocation": "Crossroads Tavern", "tension": 2},'
        '"characters": [{"name": "Old Maren", "action": "upsert", "role": "npc", "status": "alive"}],'
        '"locations": [{"name": "Crossroads Tavern", "action": "upsert", "type": "tavern"}]'
        "}\n"
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
    client, fake_openai, fake_dispatch_log, fake_commit_log
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


def test_new_session_commits_snapshot_to_git_sync(client, fake_openai, fake_commit_log):
    """Per ADR 0001 Phase 1, session creation must commit the
    initial state through git-sync after the fs-manager writes
    succeed. Verifies the commit_snapshot dispatch fires with the
    expected session_id, turn_number=0, and a summary that names
    the world."""
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

    assert len(fake_commit_log) == 1
    commit = fake_commit_log[0]
    assert commit["turn_number"] == 0
    assert "The Shattered Expanse" in commit["summary"]
    # ADR 0002: a world_id is minted, returned, and threaded into the commit.
    import uuid

    world_id = response.json()["worldId"]
    uuid.UUID(world_id)  # well-formed
    assert commit["world_id"] == world_id
    assert "Session start" in commit["summary"]
    # session_id should match the one returned in the response body
    assert commit["session_id"] == response.json()["sessionId"]


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


def test_new_session_returns_502_when_session_write_fails(
    app, fake_openai, fake_commit_log, monkeypatch
):
    """If fs-manager rejects the session-file write, the handler must
    not return a sessionId that was never persisted. It must surface
    the failure as a 502 so the frontend can react instead of
    quietly handing back an unusable ID.

    Also verifies that commit_snapshot STILL fires before the 502 —
    the Fact-Extractor dispatch succeeded and wrote world state to
    disk, so that state must make it into the git audit trail even
    though the session file itself didn't land."""
    import engine
    import engine.dispatch.fs_manager as dispatcher_module
    from fastapi.testclient import TestClient

    fake_openai.chat.completions.set_blocking_response(_opening_response())

    # Override the dispatcher to fail on the *second* dispatch (the
    # session-file write). First dispatch (Fact-Extractor payload)
    # still succeeds so we isolate the session-write failure path.
    calls = {"count": 0}

    def failing_dispatch(config, payload, *, world_id=None, client=None, timeout=30.0):
        calls["count"] += 1
        if calls["count"] == 1:
            return engine.DispatchResult(
                ok=True, status_code=200, body={"success": True}
            )
        return engine.DispatchResult(
            ok=False,
            status_code=503,
            body={"detail": "fs-manager offline"},
            error="fs-manager rejected payload (503): fs-manager offline",
        )

    monkeypatch.setattr(dispatcher_module, "apply_world_update", failing_dispatch)
    monkeypatch.setattr(engine, "apply_world_update", failing_dispatch)

    client = TestClient(app)
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Unreliable",
            "playerCharacterName": "Doomed",
            "playerCharacterClass": "Hero",
        },
    )

    assert response.status_code == 502
    assert "Failed to persist new session" in response.json()["detail"]
    assert "fs-manager offline" in response.json()["detail"]
    # Both dispatches were attempted: fact-extractor first, then session.
    assert calls["count"] == 2

    # Critical: commit_snapshot MUST still fire even though we're
    # about to 502. Otherwise the world state mutations from the
    # successful first dispatch exist on disk but not in git
    # history — a silent audit gap exactly in the failure mode
    # ADR 0001 is meant to be durable against.
    assert len(fake_commit_log) == 1
    assert "Session start" in fake_commit_log[0]["summary"]
    assert "Unreliable" in fake_commit_log[0]["summary"]


def _intro_with_pc(archetype: str, hp_max: int) -> str:
    """An intro that establishes the PC with an archetype and DM-invented vitality."""
    import json as _j

    block = _j.dumps(
        {
            "characters": [
                {
                    "name": "Mira",
                    "action": "upsert",
                    "role": "player",
                    "class": "Proctor",
                    "archetype": archetype,
                    "module_data": {
                        "character_sheet": {
                            "stats": {"body": 6, "mind": 5, "heart": 5, "will": 5},
                            "hp": {"current": hp_max, "max": hp_max},
                        }
                    },
                }
            ]
        }
    )
    return f"You wake in the ward.\n<world_update>\n{block}\n</world_update>"


def _pc_from(payload: dict) -> dict | None:
    for op in payload.get("updates", []):
        if str(op.get("target_file", "")).endswith("/entities/mira.json"):
            return op["data"]
    return None


def test_intro_hint_vitality_matches_the_persisted_entity(
    client, fake_openai, fake_dispatch_log
):
    """RFC-0019: the returned world_updates hint must carry the SAME engine-derived
    pools the intro dispatch persists. WorldCreation.jsx applies the hint directly
    and hydration is skipped after creation, so a mismatch would show the DM's
    invented vitality until a reload (coderabbit + codex)."""
    fake_openai.chat.completions.set_blocking_response(_intro_with_pc("cleric", 20))

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Ward of Ash",
            "playerCharacterName": "Mira",
            "playerCharacterClass": "Proctor",
        },
    )
    assert response.status_code == 200

    persisted = _pc_from(fake_dispatch_log[0]["payload"])
    assert persisted is not None
    persisted_sheet = persisted["module_data"]["character_sheet"]
    # Body 6 × cleric factor 6, seeded full — not the DM's 20/20.
    assert persisted_sheet["hp"] == {"current": 36, "max": 36}
    assert persisted_sheet["magic_pool"] == {"current": 10, "max": 10}

    hint_pc = next(
        c
        for c in response.json()["turns"][0]["worldUpdates"]["characters"]
        if c.get("name") == "Mira"
    )
    hint_sheet = hint_pc["module_data"]["character_sheet"]
    assert hint_sheet["hp"] == persisted_sheet["hp"]
    assert hint_sheet["magic_pool"] == persisted_sheet["magic_pool"]


def test_intro_drops_an_invalid_archetype_from_both_payload_and_hint(
    client, fake_openai, fake_dispatch_log
):
    fake_openai.chat.completions.set_blocking_response(_intro_with_pc("paladin", 20))

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Ward of Ash",
            "playerCharacterName": "Mira",
            "playerCharacterClass": "Proctor",
        },
    )
    assert response.status_code == 200

    persisted = _pc_from(fake_dispatch_log[0]["payload"])
    assert "archetype" not in persisted  # unresolvable slug never stored
    # …and it doesn't linger in the UI either.
    hint_pc = next(
        c
        for c in response.json()["turns"][0]["worldUpdates"]["characters"]
        if c.get("name") == "Mira"
    )
    assert "archetype" not in hint_pc
    # No archetype → no engine-derived vitality; the DM's value stands (fail-safe).
    assert persisted["module_data"]["character_sheet"]["hp"] == {
        "current": 20,
        "max": 20,
    }


def test_blank_player_character_name_is_rejected(client, fake_openai):
    """codex: a blank/whitespace name disabled `enforce_pc_identity` AND sent
    `find_player_character` to its legacy first-`role:"player"` scan — recreating
    the shadowing bypass the entity-identity hardening closes. It's the anchor for
    PC identity, so it must not be blank."""
    for bad in ["", "   ", "\t"]:
        resp = client.post(
            "/api/session/new",
            json={
                "worldName": "W",
                "playerCharacterName": bad,
                "playerCharacterClass": "Adventurer",
            },
        )
        assert resp.status_code == 422, bad
    # …and a padded name is accepted, stripped (so the slug/anchor is stable).
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    ok = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "  Sal  ",
            "playerCharacterClass": "Adventurer",
        },
    )
    assert ok.status_code == 200
    # Full equality: `startswith("... Sal ")` would still pass if TRAILING
    # whitespace survived the strip (coderabbit).
    assert ok.json()["turns"][0]["playerAction"] == (
        "[Session Start] Sal the Adventurer begins their journey in W."
    )
