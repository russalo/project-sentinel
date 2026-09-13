"""RFC-0018 — derived maxes at the /api/stream seam (the backend wiring).

Proves what the pure-core tests can't: a level-up turn routes through
``resolve_class_rules`` → ``enforce_progression`` and the engine-forced
``hp.max`` / ``magic_pool.max`` reach the dispatched payload — and that a
free-text class fails safe (the DM's max survives) end-to-end.
"""

import json
from pathlib import Path

PC = "Bran"
SESSION_LEVELUP = "a1a1a1a1-1111-4111-8111-a1a1a1a1a1a1"
SESSION_FAILSAFE = "b2b2b2b2-2222-4222-8222-b2b2b2b2b2b2"


def _prime_session(
    data_dir: Path, session_id: str, *, pending_level_up: dict | None = None
) -> None:
    d = data_dir / "state" / "core" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    record = {
        "session_id": session_id,
        "world_name": "Test World",
        "started_at": "2026-07-27T00:00:00Z",
        "turns": [],
        "active": True,
        "world_id": "7c0ffee0-0000-4000-8000-000000000000",
        "player_character_name": PC,
    }
    if pending_level_up is not None:
        # Item 6: enactment tests must carry a server-recorded proposal or the
        # gate strips the levelUp body.
        record["pending_level_up"] = pending_level_up
    (d / f"{session_id}.json").write_text(json.dumps(record), encoding="utf-8")


def _prime_pc(data_dir: Path, *, pc_class: str, body: int, hp: dict) -> None:
    d = data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bran.json").write_text(
        json.dumps(
            {
                "name": PC,
                "role": "player",
                "status": "alive",
                "class": pc_class,
                "level": 2,
                "module_data": {
                    "character_sheet": {
                        "stats": {"body": body, "mind": 5, "heart": 5, "will": 5},
                        "hp": hp,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _pc_op_any(dispatch_log: list):
    """The PC's entity op wherever it landed — enactment turns now lead with
    the durable proposal-consume session write, so the entity payload is not
    always dispatch_log[0]."""
    for entry in dispatch_log:
        found = _pc_op(entry["payload"])
        if found is not None:
            return found
    return None


def _pc_op(payload: dict) -> dict | None:
    for op in payload.get("updates", []):
        if str(op.get("target_file", "")).endswith("/entities/bran.json"):
            return op
    return None


def test_body_level_up_forces_derived_hp_max_end_to_end(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # A Warrior (Body 6, 48/48 HP) enacts a Body level-up. The engine commits
    # Body 7 → hp.max = 7×8 = 56, current bumped 48 → 56 — even though the DM
    # writes no <world_update> (the synth path appends the PC op).
    _prime_session(
        tmp_data_dir, SESSION_LEVELUP, pending_level_up={"to_level": 3, "turn": 1}
    )
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    fake_openai.chat.completions.set_stream_tokens(
        ["The trial tempers you — you stand taller than before."]
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "claim the growth",
            "sessionId": SESSION_LEVELUP,
            "levelUp": {"stat": "body", "toLevel": 3},
        },
    )
    assert resp.status_code == 200
    _ = resp.text  # drain the generator

    op = _pc_op_any(fake_dispatch_log)
    assert op is not None
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["stats"]["body"] == 7  # engine-committed raise
    assert sheet["hp"]["max"] == 56  # 7×8, engine-derived
    assert sheet["hp"]["current"] == 56  # bumped by the +8 delta


def test_free_text_class_leaves_dm_max_end_to_end(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # A Proctor (free-text class, no archetype factor) → fail-safe: the DM's
    # hp.max write survives untouched through the whole dispatch path.
    _prime_session(tmp_data_dir, SESSION_FAILSAFE)
    _prime_pc(tmp_data_dir, pc_class="Proctor", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {
            "characters": [
                {
                    "name": "Bran",
                    "action": "upsert",
                    "module_data": {
                        "character_sheet": {"hp": {"current": 60, "max": 60}}
                    },
                }
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["You feel hardier. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream",
        json={"action": "press on", "sessionId": SESSION_FAILSAFE},
    )
    assert resp.status_code == 200
    _ = resp.text

    op = _pc_op_any(fake_dispatch_log)
    assert op is not None
    hp = op["data"]["module_data"]["character_sheet"]["hp"]
    assert hp["max"] == 60  # DM value survives — engine doesn't own this class's max


SESSION_HINT = "c3c3c3c3-3333-4333-8333-c3c3c3c3c3c3"


def test_dm_inflated_max_never_reaches_the_sse_hint(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # RFC-0018 fast-follow: on an ORDINARY turn (no level-up) a DM-written inflated
    # hp.max must be corrected in the live hint too — not just the persisted payload.
    # Nothing re-hydrates per turn, so an uncorrected hint would stick until reload.
    _prime_session(tmp_data_dir, SESSION_HINT)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {
            "characters": [
                {
                    "name": "Bran",
                    "action": "upsert",
                    "module_data": {
                        "character_sheet": {
                            "hp": {"current": 30, "max": 999},
                            "magic_pool": {"current": 5, "max": 10},
                        }
                    },
                }
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["A blow lands. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "take the hit", "sessionId": SESSION_HINT}
    )
    assert resp.status_code == 200
    body = resp.text

    # The emitted hint carries the authoritative max (6×8=48), not the DM's 999,
    # and no magic_pool for a Warrior.
    hint_events = [
        json.loads(line[len("data: ") :])
        for line in body.split("\n")
        if line.startswith("data: ") and '"world_update"' in line
    ]
    assert hint_events, "expected a world_update event"
    pc_hint = next(
        c for c in hint_events[0]["data"]["characters"] if c.get("name") == "Bran"
    )
    hint_sheet = pc_hint["module_data"]["character_sheet"]
    assert hint_sheet["hp"] == {"current": 30, "max": 48}  # corrected, current kept
    # Non-caster pool stripped via an explicit deletion marker — an absent key
    # would mean "preserve stored" to the client reducer.
    assert hint_sheet["magic_pool"] is None

    # …and the persisted payload agrees (the shared verdict).
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["module_data"]["character_sheet"]["hp"]["max"] == 48


SESSION_ARCH = "d4d4d4d4-4444-4444-8444-d4d4d4d4d4d4"


def _prime_pc_with_archetype(data_dir: Path, *, pc_class: str, archetype: str | None):
    d = data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    pc = {
        "name": PC,
        "role": "player",
        "status": "alive",
        "class": pc_class,
        "level": 2,
        "module_data": {
            "character_sheet": {"stats": {"body": 6, "mind": 5, "heart": 5, "will": 5}}
        },
    }
    if archetype is not None:
        pc["archetype"] = archetype
    (d / "bran.json").write_text(json.dumps(pc), encoding="utf-8")


def test_archetype_gives_a_free_text_class_engine_owned_maxes(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # RFC-0019 payoff: a "Proctor" pinned to cleric now gets engine-derived
    # hp.max = Body6 × 6 = 36 and a caster pool (Will5 × 2 = 10) — where the same
    # PC without an archetype stays fail-safe (see the sibling test below).
    _prime_session(tmp_data_dir, SESSION_ARCH)
    _prime_pc_with_archetype(tmp_data_dir, pc_class="Proctor", archetype="cleric")
    # An ordinary PC write (enforcement rides existing PC ops; it only appends one
    # for an enacted level-up).
    world_update = json.dumps(
        {
            "characters": [
                {"name": "Bran", "action": "upsert", "currentLocation": "The Mill"}
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["You steady yourself. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "look around", "sessionId": SESSION_ARCH}
    )
    assert resp.status_code == 200
    _ = resp.text

    op = _pc_op_any(fake_dispatch_log)
    assert op is not None
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["hp"]["max"] == 36  # 6 × cleric factor 6
    assert sheet["magic_pool"]["max"] == 10  # Will 5 × 2, a caster
    assert op["data"]["archetype"] == "cleric"  # pinned on every op


def test_dm_cannot_remap_archetype_end_to_end(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # The attack: re-map cleric → warrior mid-session for a bigger HP factor.
    _prime_session(tmp_data_dir, SESSION_ARCH)
    _prime_pc_with_archetype(tmp_data_dir, pc_class="Proctor", archetype="cleric")
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "archetype": "warrior"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["You feel like a new person. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "reinvent myself", "sessionId": SESSION_ARCH}
    )
    assert resp.status_code == 200
    body = resp.text

    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["archetype"] == "cleric"  # re-map overridden
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["hp"]["max"] == 36  # still the cleric factor, not warrior's 48
    assert "archetype is set once" in body  # surfaced to the player


SESSION_EST = "e5e5e5e5-5555-4555-8555-e5e5e5e5e5e5"


def test_establishing_turn_derives_maxes_end_to_end(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    # An UNCLASSIFIED free-text PC is classified by the DM this turn; the same
    # dispatch must also derive the maxes (coderabbit + codex: resolving the class
    # rules from stored state alone left the classifying turn DM-authored).
    _prime_session(tmp_data_dir, SESSION_EST)
    _prime_pc_with_archetype(tmp_data_dir, pc_class="Proctor", archetype=None)
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "archetype": "cleric"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        [
            "You are, at heart, a healer. ",
            f"<world_update>{world_update}</world_update>",
        ]
    )

    resp = client.post(
        "/api/stream", json={"action": "tend the wounded", "sessionId": SESSION_EST}
    )
    assert resp.status_code == 200
    _ = resp.text

    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["archetype"] == "cleric"
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["hp"]["max"] == 36  # Body 6 x cleric 6 — on the SAME turn
    assert sheet["magic_pool"]["max"] == 10


def test_invalid_archetype_never_persists_end_to_end(
    client, fake_openai, fake_dispatch_log, fake_commit_log, tmp_data_dir
):
    _prime_session(tmp_data_dir, SESSION_EST)
    _prime_pc_with_archetype(tmp_data_dir, pc_class="Proctor", archetype=None)
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "archetype": "paladin"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["A holy warrior. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post("/api/stream", json={"action": "pray", "sessionId": SESSION_EST})
    assert resp.status_code == 200
    _ = resp.text

    op = _pc_op_any(fake_dispatch_log)
    assert "archetype" not in op["data"]  # unresolvable slug never stored


# ── Item 5: current clamp + every-turn level/stats hint mirror ────────────────

SESSION_CLAMP = "e5e5e5e5-5555-4555-8555-e5e5e5e5e5e5"
SESSION_LEVEL99 = "f6f6f6f6-6666-4666-8666-f6f6f6f6f6f6"


def test_injected_current_9999_clamped_end_to_end(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """THE EXPLOIT REGRESSION (playtest 2026-09-13): hp.current 9999 injected
    via <world_update> used to persist verbatim → unkillable PC. Now: persisted
    current == max, displayed current == max, player notice emitted."""
    _prime_session(tmp_data_dir, SESSION_CLAMP)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 40, "max": 48})
    world_update = json.dumps(
        {
            "characters": [
                {
                    "name": "Bran",
                    "action": "upsert",
                    "module_data": {"character_sheet": {"hp": {"current": 9999}}},
                }
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Vigor floods you. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream",
        json={"action": "declare myself immortal", "sessionId": SESSION_CLAMP},
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: ") :])
        for line in resp.text.split("\n")
        if line.startswith("data: ") and line[len("data: ") :].strip() != "[DONE]"
    ]

    # Persisted: clamped to the engine max (6×8=48).
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["module_data"]["character_sheet"]["hp"] == {
        "current": 48,
        "max": 48,
    }
    # Displayed: the SAME value (shared clamp rule) — not 9999 until reload.
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    pc_hint = next(c for c in hint["characters"] if c.get("name") == "Bran")
    assert pc_hint["module_data"]["character_sheet"]["hp"] == {
        "current": 48,
        "max": 48,
    }
    # Player notice.
    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert any("clamped" in n for n in notices)


def test_dm_level_99_hint_normalized_on_ordinary_turn(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """Item 5b (playtest 2026-09-13): the persisted level was already forced
    every turn, but the hint mirror ran only on levelUp turns — a DM hint
    carrying level:99 displayed until reload. Now every turn normalizes."""
    _prime_session(tmp_data_dir, SESSION_LEVEL99)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {
            "characters": [
                {
                    "name": "Bran",
                    "action": "upsert",
                    "level": 99,
                    "module_data": {
                        "character_sheet": {
                            "stats": {"body": 9, "mind": 9, "heart": 9, "will": 9}
                        }
                    },
                }
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Power surges. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "ascend", "sessionId": SESSION_LEVEL99}
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: ") :])
        for line in resp.text.split("\n")
        if line.startswith("data: ") and line[len("data: ") :].strip() != "[DONE]"
    ]
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    pc_hint = next(c for c in hint["characters"] if c.get("name") == "Bran")
    # Displayed == persisted: the stored level (2) and stored stats — not the
    # DM's 99s.
    assert pc_hint["level"] == 2
    assert pc_hint["module_data"]["character_sheet"]["stats"] == {
        "body": 6,
        "mind": 5,
        "heart": 5,
        "will": 5,
    }
    # …and the persisted payload agrees (already enforced pre-Item-5).
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["level"] == 2


# ── Item 6a: the server-side proposal gate ────────────────────────────────────

SESSION_UNPROMPTED = "a7a7a7a7-7777-4777-8777-a7a7a7a7a7a7"
SESSION_PROPOSE = "b8b8b8b8-8888-4888-8888-b8b8b8b8b8b8"
SESSION_CAPPED = "c9c9c9c9-9999-4999-8999-c9c9c9c9c9c9"


def _events_of(resp):
    return [
        json.loads(line[len("data: ") :])
        for line in resp.text.split("\n")
        if line.startswith("data: ") and line[len("data: ") :].strip() != "[DONE]"
    ]


def test_unprompted_enactment_is_stripped_end_to_end(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """THE EXPLOIT REGRESSION (playtest 2026-09-13): with no server-recorded
    proposal, {levelUp} used to grant +1 level per turn (1→5 in 4 turns). Now
    the enactment is stripped before the DM prompt, enforcement, and mirrors —
    with a player notice."""
    _prime_session(tmp_data_dir, SESSION_UNPROMPTED)  # NO pending proposal
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "status": "alive"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Nothing is earned. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "I level up",
            "sessionId": SESSION_UNPROMPTED,
            "levelUp": {"stat": "body", "toLevel": 3},
        },
    )
    assert resp.status_code == 200
    events = _events_of(resp)

    # Player notice, and the persisted PC keeps its stored level + stats.
    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert any("No level-up has been proposed" in n for n in notices)
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["level"] == 2
    assert op["data"]["module_data"]["character_sheet"]["stats"]["body"] == 6

    # The DM prompt never saw a rendered LEVEL-UP CHOICE block. (The phrase
    # "LEVEL-UP CHOICE:" also appears in the milestone module's standing
    # prompt text, so the assertion targets dm.py's rendered block shape.)
    sent = json.dumps(fake_openai.chat.completions.calls[-1]["messages"])
    assert "LEVEL-UP CHOICE: the player advances" not in sent


def test_dm_proposal_is_recorded_with_the_engines_number(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """A DM level_up proposal records pending_level_up in the session write —
    with the ENGINE's stored+1, not the DM's hallucinated to_level."""
    _prime_session(tmp_data_dir, SESSION_PROPOSE)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {
            "characters": [{"name": "Bran", "action": "upsert", "status": "alive"}],
            "level_up": {"to_level": 9},  # advisory, hallucinated
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["The trial tempers you. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "survive", "sessionId": SESSION_PROPOSE}
    )
    assert resp.status_code == 200

    session_payload = next(
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    )
    recorded = session_payload["updates"][0]["data"]["pending_level_up"]
    assert recorded == {"to_level": 3, "turn": 1}  # stored 2 + 1, NOT 9


def test_enactment_consumes_the_pending_proposal(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    _prime_session(
        tmp_data_dir, SESSION_PROPOSE, pending_level_up={"to_level": 3, "turn": 1}
    )
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "status": "alive"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Strength settles in. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "take the level",
            "sessionId": SESSION_PROPOSE,
            "levelUp": {"stat": "body", "toLevel": 3},
        },
    )
    assert resp.status_code == 200

    # Enacted: level 3, body 7, grown max (7×8=56) persisted…
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["level"] == 3
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["stats"]["body"] == 7
    assert sheet["hp"]["max"] == 56
    # …and the proposal is CONSUMED durably FIRST (codex P1/coderabbit Major
    # on #201): the very first dispatch is a session write with the pending
    # cleared, BEFORE the progression dispatch — a session-write failure
    # later can no longer leave a pending proposal beside an applied level.
    first = fake_dispatch_log[0]["payload"]
    assert "sessions" in first["updates"][0]["target_file"]
    assert first["updates"][0]["data"]["pending_level_up"] is None
    # The final (turn-carrying) session write agrees.
    last_session = [
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    ][-1]
    assert last_session["updates"][0]["data"]["pending_level_up"] is None


def test_proposal_at_cap_is_not_recorded(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    _prime_session(tmp_data_dir, SESSION_CAPPED)
    d = tmp_data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    d.joinpath("bran.json").write_text(
        json.dumps(
            {
                "name": PC,
                "role": "player",
                "status": "alive",
                "class": "Warrior",
                "level": 5,
                "module_data": {
                    "character_sheet": {
                        "stats": {"body": 6, "mind": 5, "heart": 5, "will": 5},
                        "hp": {"current": 48, "max": 48},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    world_update = json.dumps(
        {
            "characters": [{"name": "Bran", "action": "upsert", "status": "alive"}],
            "level_up": {"to_level": 6},
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Even legends rest. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream", json={"action": "triumph", "sessionId": SESSION_CAPPED}
    )
    assert resp.status_code == 200
    session_payload = next(
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    )
    assert session_payload["updates"][0]["data"]["pending_level_up"] is None


def test_primed_pending_at_cap_bumps_nothing(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """Defense-in-depth (6b through the route): even with a crafted pending
    proposal, an at-cap enactment changes neither level nor stats — with the
    cap notice."""
    _prime_session(
        tmp_data_dir, SESSION_CAPPED, pending_level_up={"to_level": 6, "turn": 3}
    )
    d = tmp_data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    d.joinpath("bran.json").write_text(
        json.dumps(
            {
                "name": PC,
                "role": "player",
                "status": "alive",
                "class": "Warrior",
                "level": 5,
                "module_data": {
                    "character_sheet": {
                        "stats": {"body": 6, "mind": 5, "heart": 5, "will": 5},
                        "hp": {"current": 48, "max": 48},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "status": "alive"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["The summit holds. ", f"<world_update>{world_update}</world_update>"]
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "ascend further",
            "sessionId": SESSION_CAPPED,
            "levelUp": {"stat": "body"},
        },
    )
    assert resp.status_code == 200
    events = _events_of(resp)
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["level"] == 5
    sheet = op["data"]["module_data"]["character_sheet"]
    assert sheet["stats"]["body"] == 6
    assert sheet["hp"] == {"current": 48, "max": 48}
    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert any("level cap" in n for n in notices)


SESSION_R2 = "d1d1d1d1-aaaa-4aaa-8aaa-d1d1d1d1d1d1"


def test_consume_write_failure_degrades_to_ordinary_turn(
    app, fake_openai, monkeypatch, tmp_data_dir
):
    """If the durable consume write fails, the enactment degrades — the
    proposal stays on disk (retryable), nothing levels, and the player is
    told. Fail-closed toward the double-apply exploit."""
    import engine
    import engine.dispatch.fs_manager as dispatcher_module
    from fastapi.testclient import TestClient

    _prime_session(
        tmp_data_dir, SESSION_R2, pending_level_up={"to_level": 3, "turn": 1}
    )
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})

    calls = {"n": 0}

    def failing_first_session_write(
        config, payload, *, world_id=None, client=None, timeout=30.0
    ):
        calls["n"] += 1
        if calls["n"] == 1:  # the consume write is the FIRST dispatch
            return engine.DispatchResult(
                ok=False, status_code=503, body={}, error="fs-manager offline"
            )
        return engine.DispatchResult(ok=True, status_code=200, body={"success": True})

    monkeypatch.setattr(
        dispatcher_module, "apply_world_update", failing_first_session_write
    )
    monkeypatch.setattr(engine, "apply_world_update", failing_first_session_write)

    world_update = json.dumps(
        {"characters": [{"name": "Bran", "action": "upsert", "status": "alive"}]}
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["The moment slips. ", f"<world_update>{world_update}</world_update>"]
    )
    client = TestClient(app)
    resp = client.post(
        "/api/stream",
        json={
            "action": "take the level",
            "sessionId": SESSION_R2,
            "levelUp": {"stat": "body"},
        },
    )
    assert resp.status_code == 200
    events = _events_of(resp)
    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert any("could not be recorded" in n for n in notices)
    # No LEVEL-UP CHOICE block reached the DM; nothing leveled.
    sent = json.dumps(fake_openai.chat.completions.calls[-1]["messages"])
    assert "LEVEL-UP CHOICE: the player advances" not in sent


def test_malformed_proposal_normalized_in_hint_and_recorded(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """coderabbit P2 on #201: a malformed DM proposal ({}) used to record an
    INVISIBLE pending (the SPA rejects the shape → no card) that a crafted
    request could enact. The hint's level_up is now REPLACED with the
    engine-derived target — displayed == gated (#189)."""
    _prime_session(tmp_data_dir, SESSION_R2)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    world_update = json.dumps(
        {
            "characters": [{"name": "Bran", "action": "upsert", "status": "alive"}],
            "level_up": {},
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["Growth beckons. ", f"<world_update>{world_update}</world_update>"]
    )
    resp = client.post(
        "/api/stream", json={"action": "endure", "sessionId": SESSION_R2}
    )
    assert resp.status_code == 200
    events = _events_of(resp)
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    assert hint["level_up"] == {"to_level": 3}  # engine-derived, SPA-renderable
    session_payload = next(
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    )
    assert session_payload["updates"][0]["data"]["pending_level_up"] == {
        "to_level": 3,
        "turn": 1,
    }


def test_same_turn_reproposal_after_enacting_to_cap_is_ignored(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """coderabbit Minor on #201: the replacement proposal must use the
    POST-enactment level — a level-4 PC enacting to 5 (the cap) this turn
    must not get a fresh proposal recorded, and the hint card is stripped."""
    _prime_session(
        tmp_data_dir, SESSION_R2, pending_level_up={"to_level": 5, "turn": 7}
    )
    d = tmp_data_dir / "state" / "core" / "entities"
    d.mkdir(parents=True, exist_ok=True)
    d.joinpath("bran.json").write_text(
        json.dumps(
            {
                "name": PC,
                "role": "player",
                "status": "alive",
                "class": "Warrior",
                "level": 4,
                "module_data": {
                    "character_sheet": {
                        "stats": {"body": 6, "mind": 5, "heart": 5, "will": 5},
                        "hp": {"current": 48, "max": 48},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    world_update = json.dumps(
        {
            "characters": [{"name": "Bran", "action": "upsert", "status": "alive"}],
            "level_up": {"to_level": 6},  # DM same-turn re-proposal
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["The peak at last. ", f"<world_update>{world_update}</world_update>"]
    )
    resp = client.post(
        "/api/stream",
        json={
            "action": "take the final level",
            "sessionId": SESSION_R2,
            "levelUp": {"stat": "body"},
        },
    )
    assert resp.status_code == 200
    events = _events_of(resp)
    op = _pc_op_any(fake_dispatch_log)
    assert op["data"]["level"] == 5  # enacted to cap
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    assert "level_up" not in hint  # no card for a proposal the gate won't honor
    last_session = [
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    ][-1]
    assert last_session["updates"][0]["data"]["pending_level_up"] is None


def test_short_nonempty_narrative_session_write_is_schema_safe(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """codex on #201 (pre-existing): `narrative[:200] or fallback` only caught
    EMPTY — a short nonempty narrative ("Done.") sent a <10-char log_entry
    and 422'd the whole session write."""
    _prime_session(tmp_data_dir, SESSION_R2)
    _prime_pc(tmp_data_dir, pc_class="Warrior", body=6, hp={"current": 48, "max": 48})
    fake_openai.chat.completions.set_stream_tokens(["Done."])
    resp = client.post("/api/stream", json={"action": "nod", "sessionId": SESSION_R2})
    assert resp.status_code == 200
    session_payload = next(
        entry["payload"]
        for entry in fake_dispatch_log
        if "sessions" in entry["payload"]["updates"][0]["target_file"]
    )
    assert len(session_payload["log_entry"]) >= 10
