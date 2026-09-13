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


def _prime_session(data_dir: Path, session_id: str) -> None:
    d = data_dir / "state" / "core" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_name": "Test World",
                "started_at": "2026-07-27T00:00:00Z",
                "turns": [],
                "active": True,
                "world_id": "7c0ffee0-0000-4000-8000-000000000000",
                "player_character_name": PC,
            }
        ),
        encoding="utf-8",
    )


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
    _prime_session(tmp_data_dir, SESSION_LEVELUP)
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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
    op = _pc_op(fake_dispatch_log[0]["payload"])
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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

    op = _pc_op(fake_dispatch_log[0]["payload"])
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
    op = _pc_op(fake_dispatch_log[0]["payload"])
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
    op = _pc_op(fake_dispatch_log[0]["payload"])
    assert op["data"]["level"] == 2
