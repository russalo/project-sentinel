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

    # Three dispatches: (1) the deterministic PC provisioning (ADR-0004),
    # (2) the Fact-Extractor payload for the world/entity state, (3) the
    # session-metadata write. Provisioning comes FIRST so the DM's own
    # fragments shallow-merge onto the skeleton.
    assert len(fake_dispatch_log) == 3

    prov_payload = fake_dispatch_log[0]["payload"]
    (prov_op,) = prov_payload["updates"]
    assert prov_op["operation"] == "create"
    assert prov_op["target_file"] == "data/state/core/entities/p.json"
    assert prov_op["data"]["role"] == "player"
    assert prov_op["data"]["level"] == 1
    # Same world on every dispatch — per-world routing threads through all
    # three, including the session-metadata write (coderabbit).
    world_id = response.json()["worldId"]
    assert {entry["world_id"] for entry in fake_dispatch_log} == {world_id}

    fact_payload = fake_dispatch_log[1]["payload"]
    targets = {u["target_file"] for u in fact_payload["updates"]}
    assert "data/state/core/world/state.json" in targets
    assert "data/state/core/entities/old_maren.json" in targets
    assert "data/state/core/locations/crossroads_tavern.json" in targets

    session_payload = fake_dispatch_log[2]["payload"]
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
    The Fact-Extractor returns payload=None so there's no world-state
    dispatch — but the PC entity is STILL provisioned (the live-world
    regression this feature closes: a DM that never emits the PC used to
    leave ADR-0004 enforcement with nothing to anchor on), followed by
    the session-metadata write."""
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

    # Two dispatches: PC provisioning, then the session metadata write.
    assert len(fake_dispatch_log) == 2
    prov_op = fake_dispatch_log[0]["payload"]["updates"][0]
    assert prov_op["target_file"] == "data/state/core/entities/ghost.json"
    assert prov_op["operation"] == "create"
    assert prov_op["data"]["role"] == "player"
    assert "sessions" in fake_dispatch_log[1]["payload"]["updates"][0]["target_file"]


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

    # Override the dispatcher to fail on the *third* dispatch (the
    # session-file write). PC provisioning and the Fact-Extractor payload
    # still succeed so we isolate the session-write failure path.
    calls = {"count": 0}

    def failing_dispatch(config, payload, *, world_id=None, client=None, timeout=30.0):
        calls["count"] += 1
        if calls["count"] <= 2:
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
    # All three dispatches were attempted: provisioning, fact-extractor, session.
    assert calls["count"] == 3

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

    persisted = _pc_from(fake_dispatch_log[1]["payload"])
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

    persisted = _pc_from(fake_dispatch_log[1]["payload"])
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


# ── deterministic PC provisioning (ADR-0004) ─────────────────────────


def _selective_dispatch(monkeypatch, provisioning_result):
    """Patch the dispatcher so the PC-provisioning dispatch (a single-op
    `create` on an entities path) returns ``provisioning_result`` while every
    other dispatch succeeds. Returns the call log."""
    import engine
    import engine.dispatch.fs_manager as dispatcher_module

    log = []

    def dispatch(config, payload, *, world_id=None, client=None, timeout=30.0):
        log.append({"payload": payload, "world_id": world_id})
        ops = payload.get("updates", [])
        if (
            len(ops) == 1
            and ops[0].get("operation") == "create"
            and "/entities/" in str(ops[0].get("target_file"))
        ):
            return provisioning_result
        return engine.DispatchResult(ok=True, status_code=200, body={"success": True})

    monkeypatch.setattr(dispatcher_module, "apply_world_update", dispatch)
    monkeypatch.setattr(engine, "apply_world_update", dispatch)
    return log


def test_established_archetype_pin_beats_the_dm_intro(
    client, fake_openai, fake_dispatch_log
):
    """The creation payload named a known archetype ("Warrior"), so the engine
    provisions it — and a DM intro claiming a different one for the PC is
    overwritten in BOTH the persisted payload and the displayed hint."""
    import json as _j

    block = _j.dumps(
        {
            "characters": [
                {
                    "name": "Mira",
                    "action": "upsert",
                    "role": "player",
                    "archetype": "mage",
                    "module_data": {
                        "character_sheet": {
                            "stats": {"body": 6, "mind": 5, "heart": 5, "will": 5}
                        }
                    },
                }
            ]
        }
    )
    fake_openai.chat.completions.set_blocking_response(
        f"You wake in the ward.\n<world_update>\n{block}\n</world_update>"
    )

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Ward of Ash",
            "playerCharacterName": "Mira",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 200

    # The provisioned skeleton pinned the archetype…
    prov_data = fake_dispatch_log[0]["payload"]["updates"][0]["data"]
    assert prov_data["archetype"] == "warrior"
    # …the DM's conflicting claim is overwritten in the persisted payload…
    persisted = _pc_from(fake_dispatch_log[1]["payload"])
    assert persisted["archetype"] == "warrior"
    # …with warrior-derived vitality (body 6 × 8), not mage's…
    assert persisted["module_data"]["character_sheet"]["hp"] == {
        "current": 48,
        "max": 48,
    }
    # …and the hint mirrors both (the #189 lesson).
    hint_pc = next(
        c
        for c in response.json()["turns"][0]["worldUpdates"]["characters"]
        if c.get("name") == "Mira"
    )
    assert hint_pc["archetype"] == "warrior"
    assert hint_pc["module_data"]["character_sheet"]["hp"] == {
        "current": 48,
        "max": 48,
    }


def test_dm_level_claim_is_stripped_and_hint_pinned_to_establishment(
    client, fake_openai, fake_dispatch_log
):
    """`level` is engine-owned (RFC-0017) and the intro runs no enforcement —
    a DM intro emitting one for the PC must not shallow-merge over the
    provisioned level 1, and the hint must show the committed value."""
    import json as _j

    block = _j.dumps(
        {
            "characters": [
                {"name": "Kael", "action": "upsert", "role": "player", "level": 7},
                {"name": "Goblin", "action": "upsert", "role": "npc", "level": 3},
            ]
        }
    )
    fake_openai.chat.completions.set_blocking_response(
        f"A road, a fork.\n<world_update>\n{block}\n</world_update>"
    )

    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Wanderer",
        },
    )
    assert response.status_code == 200

    fact_payload = fake_dispatch_log[1]["payload"]
    pc_op = next(
        u["data"]
        for u in fact_payload["updates"]
        if u["target_file"].endswith("/entities/kael.json")
    )
    assert "level" not in pc_op  # the provisioned level 1 stands on disk
    npc_op = next(
        u["data"]
        for u in fact_payload["updates"]
        if u["target_file"].endswith("/entities/goblin.json")
    )
    assert npc_op["level"] == 3  # NPCs are the DM's

    chars = response.json()["turns"][0]["worldUpdates"]["characters"]
    hint_pc = next(c for c in chars if c["name"] == "Kael")
    assert hint_pc["level"] == 1  # displayed = persisted
    hint_npc = next(c for c in chars if c["name"] == "Goblin")
    assert hint_npc["level"] == 3


def test_provisioning_409_is_the_idempotency_path(
    app, fake_openai, fake_commit_log, monkeypatch
):
    """fs-manager 409s a `create` whose target exists — the entity survives
    from a prior shared-tree session. The session still creates, nothing is
    re-minted, and NO establishment pins apply: the stored entity (not the new
    session's class text) is authoritative, so the DM's valid archetype claim
    passes through and the hint level is stripped rather than pinned to 1."""
    import engine
    import json as _j
    from fastapi.testclient import TestClient

    log = _selective_dispatch(
        monkeypatch,
        engine.DispatchResult(
            ok=False,
            status_code=409,
            body={"detail": {"code": "FILE_EXISTS"}},
            error="fs-manager rejected payload (409): exists",
        ),
    )

    block = _j.dumps(
        {
            "characters": [
                {
                    "name": "Kael",
                    "action": "upsert",
                    "role": "player",
                    "archetype": "mage",
                    "level": 7,
                }
            ]
        }
    )
    fake_openai.chat.completions.set_blocking_response(
        f"You return.\n<world_update>\n{block}\n</world_update>"
    )

    client = TestClient(app)
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 200
    assert len(log) == 3  # provisioning (409), fact payload, session write

    pc_op = next(
        u["data"]
        for u in log[1]["payload"]["updates"]
        if u["target_file"].endswith("/entities/kael.json")
    )
    # Write-once (RFC-0019): even a VALID DM archetype claim is dropped on the
    # 409 path — the STORED pin is authoritative and the intro runs no
    # enforcement, so merging it would overwrite write-once (coderabbit).
    assert "archetype" not in pc_op
    # level stays engine-owned: stripped so the STORED level survives the merge.
    assert "level" not in pc_op

    chars = response.json()["turns"][0]["worldUpdates"]["characters"]
    hint_pc = next(c for c in chars if c["name"] == "Kael")
    # Stripped, not pinned — the stored level isn't known at this seam, and
    # showing nothing beats showing a DM invention. Same for the archetype
    # claim the write seam just dropped (#189: displayed == persisted).
    assert "level" not in hint_pc
    assert "archetype" not in hint_pc


def test_provisioning_failure_returns_502(app, fake_openai, monkeypatch):
    """Guaranteeing the PC entity is the point — any non-409 provisioning
    failure fails the creation loudly instead of minting a world that
    recreates the no-PC-file gap."""
    import engine
    from fastapi.testclient import TestClient

    log = _selective_dispatch(
        monkeypatch,
        engine.DispatchResult(
            ok=False,
            status_code=503,
            body={"detail": "fs-manager offline"},
            error="fs-manager rejected payload (503): fs-manager offline",
        ),
    )

    fake_openai.chat.completions.set_blocking_response(_opening_response())
    client = TestClient(app)
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 502
    assert "provisioning" in response.json()["detail"]
    assert len(log) == 1  # nothing else was written after the failure


def test_unsluggable_name_skips_provisioning_loudly(
    client, fake_openai, fake_dispatch_log, caplog
):
    """A non-ASCII name has no entity slug (pending product call — NOT solved
    here): the session still creates, no provisioning dispatch happens, and the
    gap is logged at ERROR so it can't pass silently."""
    import logging

    fake_openai.chat.completions.set_blocking_response(
        "The tavern is silent. Nothing stirs."
    )
    with caplog.at_level(logging.ERROR, logger="backend.routes.session"):
        response = client.post(
            "/api/session/new",
            json={
                "worldName": "W",
                "playerCharacterName": "李明",
                "playerCharacterClass": "Warrior",
            },
        )
    assert response.status_code == 200
    # Only the session-metadata write — no provisioning create dispatched.
    assert len(fake_dispatch_log) == 1
    assert "sessions" in fake_dispatch_log[0]["payload"]["updates"][0]["target_file"]
    assert any("no usable entity slug" in rec.message for rec in caplog.records), (
        caplog.records
    )


def test_oversized_player_name_is_rejected_at_the_boundary(client, fake_openai):
    """coderabbit (PR #196): the name becomes the entity FILENAME via the slug
    contract — an unbounded name builds an unwriteable path. 200 keeps
    slug + ".json" under the 255-byte filesystem cap."""
    resp = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "K" * 201,
            "playerCharacterClass": "Warrior",
        },
    )
    assert resp.status_code == 422
    # …and the cap itself is fine.
    fake_openai.chat.completions.set_blocking_response("A road. Nothing stirs.")
    resp = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "K" * 200,
            "playerCharacterClass": "Warrior",
        },
    )
    assert resp.status_code == 200


def test_provisioned_pc_is_synthesized_into_the_creation_hint(
    client, fake_openai, fake_dispatch_log
):
    """codex (PR #196): when the DM omits the PC (or the whole world_update),
    the UI must still learn the provisioned entity exists — WorldCreation
    applies the hint verbatim and hydration is skipped after creation."""
    fake_openai.chat.completions.set_blocking_response(
        "The tavern is silent. Nothing stirs."
    )
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Empty",
            "playerCharacterName": "Ghost",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 200
    chars = response.json()["turns"][0]["worldUpdates"]["characters"]
    (pc,) = chars
    # Displayed == persisted: the hint entry is the dispatched skeleton.
    assert pc == fake_dispatch_log[0]["payload"]["updates"][0]["data"]
    assert pc["role"] == "player"
    assert pc["level"] == 1
    assert pc["archetype"] == "warrior"


def test_hint_synthesis_defers_to_a_dm_written_pc(
    client, fake_openai, fake_dispatch_log
):
    """When the DM's hint already carries the PC, nothing is appended — the
    sanitizers own that entry (no duplicate cards)."""
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Old Maren",  # collides with the DM's NPC slug
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 200
    chars = response.json()["turns"][0]["worldUpdates"]["characters"]
    assert len([c for c in chars if c.get("name") == "Old Maren"]) == 1


def test_provisioning_failure_commits_partial_state_before_502(
    app, fake_openai, fake_commit_log, monkeypatch
):
    """codex (PR #196): fs-manager writes the entity BEFORE the session-log
    append, so a non-409 failure can leave a real write on disk — commit it
    before raising, like the session-write failure path."""
    import engine
    from fastapi.testclient import TestClient

    _selective_dispatch(
        monkeypatch,
        engine.DispatchResult(
            ok=False,
            status_code=500,
            body={"detail": "log append failed"},
            error="fs-manager rejected payload (500): log append failed",
        ),
    )
    fake_openai.chat.completions.set_blocking_response(_opening_response())
    client = TestClient(app)
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Unlucky",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 502
    assert len(fake_commit_log) == 1
    assert "provisioning failure capture" in fake_commit_log[0]["summary"]


# ── truncated-intro guard (Item 3 / playtest F3a) ────────────────────


def test_truncated_intro_retries_once_and_succeeds(
    client, fake_openai, fake_dispatch_log
):
    """finish_reason=="length" on the intro (the thinking-model budget clip)
    gets ONE clean retry on the blocking path — the player sees only the
    complete second response, and exactly one world is minted."""
    fake_openai.chat.completions.queue_blocking_responses(
        ("You step into the wastes, broken only by the mournful cre", "length"),
        (_opening_response(), "stop"),
    )
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 200
    assert len(fake_openai.chat.completions.calls) == 2  # original + one retry
    narrative = response.json()["turns"][0]["narrative"]
    assert "Crossroads Tavern" in narrative  # the retry's narrative won
    assert "mournful cre" not in narrative
    # Normal creation flow after the retry: provisioning, fact payload, session.
    assert len(fake_dispatch_log) == 3


def test_intro_truncated_twice_fails_creation_cleanly(
    client, fake_openai, fake_dispatch_log
):
    """Retry exhausted → 502 with the existing intro-failure UX, and NOTHING
    written (no half-minted world whose opening is cut mid-word). The second
    response exercises the unclosed-block BACKSTOP (no finish_reason)."""
    fake_openai.chat.completions.queue_blocking_responses(
        ("A world begins, broken only by the mournful cre", "length"),
        ('Second try. <world_update>{"world": {"tens', None),
    )
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 502
    assert "DM agent failed during intro" in response.json()["detail"]
    assert len(fake_openai.chat.completions.calls) == 2
    assert fake_dispatch_log == []  # nothing provisioned, nothing dispatched


def test_intro_retry_charges_the_llm_ceiling(app, fake_openai, monkeypatch):
    """The retry is a real second LLM call: with the daily ceiling at 1 the
    retry itself is refused (429), not silently free."""
    import dataclasses

    from fastapi.testclient import TestClient

    app.state.settings = dataclasses.replace(app.state.settings, llm_daily_ceiling=1)
    fake_openai.chat.completions.queue_blocking_responses(
        ("Clipped opening, mournful cre", "length"),
        (_opening_response(), "stop"),
    )
    client = TestClient(app)
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "W",
            "playerCharacterName": "Kael",
            "playerCharacterClass": "Warrior",
        },
    )
    assert response.status_code == 429
    # Only the first call happened — the ceiling stopped the retry.
    assert len(fake_openai.chat.completions.calls) == 1


def test_intro_collision_still_yields_the_pc_skeleton_in_the_hint(
    client, fake_openai, fake_dispatch_log
):
    """Item 7 intro-seam ordering: a slug-twin in the intro is dropped by the
    identity sanitize, and ensure_hint_pc (now AFTER it) still synthesizes
    the provisioned skeleton — running before, it would have seen the
    imposter's slug, deferred, and left the hint with no PC at all."""
    import json as _j

    pc = "Þóra Björnsdóttir"
    collider = "Ra Bj Rnsd Ttir"
    block = _j.dumps(
        {"characters": [{"name": collider, "action": "upsert", "role": "npc"}]}
    )
    fake_openai.chat.completions.set_blocking_response(
        f"Two shadows, one name.\n<world_update>\n{block}\n</world_update>"
    )
    response = client.post(
        "/api/session/new",
        json={
            "worldName": "Röstigraben",
            "playerCharacterName": pc,
            "playerCharacterClass": "Skald",
        },
    )
    assert response.status_code == 200

    # The dispatched intro payload carries no collider op…
    fact_payload = fake_dispatch_log[1]["payload"]
    for op in fact_payload["updates"]:
        if op["target_file"].endswith("/entities/ra_bj_rnsd_ttir.json"):
            assert op["data"].get("name") != collider
    # …and the hint shows the provisioned PC, not the imposter and not nothing.
    chars = response.json()["turns"][0]["worldUpdates"]["characters"]
    names = [c.get("name") for c in chars]
    assert pc in names
    assert collider not in names
