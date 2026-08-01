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
    fake_openai.chat.completions.set_stream_tokens(
        [
            "You feel hardier. ",
            '<world_update>{"characters":[{"name":"Bran","action":"upsert",'
            '"module_data":{"character_sheet":{"hp":{"current":60,"max":60}}}}]}'
            "</world_update>",
        ]
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
