"""Route-level coverage for the PC self-demotion repair (Item 4) and the
per-turn identity-notice dedupe on /api/stream.

Separate file (not test_stream.py) so it composes cleanly with the in-flight
PR #196 test additions.
"""

import json
from pathlib import Path

VALID_SESSION_ID = "66666666-7777-8888-9999-aaaaaaaaaaaa"


def _prime_session(data_dir: Path, session_id: str) -> None:
    session_dir = data_dir / "state" / "core" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "world_name": "Test World",
                "started_at": "2026-04-13T00:00:00Z",
                "turns": [],
                "active": True,
                "player_character_name": "Kael",
                "world_id": "7c0ffee0-0000-4000-8000-000000000001",
            }
        ),
        encoding="utf-8",
    )


def _events(text: str) -> list:
    out = []
    for line in text.split("\n"):
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            out.append(json.loads(line[6:]))
    return out


def _dm_response_tokens(block: dict) -> list[str]:
    full = "The air shifts.\n<world_update>\n" + json.dumps(block) + "\n</world_update>"
    return [full[i : i + 17] for i in range(0, len(full), 17)]


def test_pc_self_demotion_is_repaired_in_payload_and_hint(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """playtest 2026-09-13 (F2's second half): a DM op writing role:"npc" onto
    the REAL PC used to merge — flipping the DM's POV and orphaning the SPA's
    role === "player" lookups. Both seams now repair it, with ONE notice."""
    _prime_session(tmp_data_dir, VALID_SESSION_ID)
    fake_openai.chat.completions.set_stream_tokens(
        _dm_response_tokens(
            {
                "characters": [
                    {"name": "Kael", "action": "update", "role": "npc"},
                    {"name": "Aldric", "action": "upsert", "role": "player"},
                ]
            }
        )
    )

    response = client.post(
        "/api/stream", json={"action": "look inward", "sessionId": VALID_SESSION_ID}
    )
    assert response.status_code == 200
    events = _events(response.text)

    # Hint seam: PC repaired, imposter neutralized.
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    by_name = {c["name"]: c for c in hint["characters"]}
    assert by_name["Kael"]["role"] == "player"
    assert by_name["Aldric"]["role"] == "npc"

    # Write seam: the dispatched payload carries the same repairs.
    entity_ops = {
        u["target_file"]: u["data"]
        for entry in fake_dispatch_log
        for u in entry["payload"]["updates"]
        if "/entities/" in u["target_file"]
    }
    assert entity_ops["data/state/core/entities/kael.json"]["role"] == "player"
    assert entity_ops["data/state/core/entities/aldric.json"]["role"] == "npc"

    # Notices: one per distinct violation text — NOT doubled across the two
    # seams (playtest 2026-09-13 nit: the #192 notice used to show twice).
    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert len(notices) == len(set(notices)), notices
    assert any("remains the player character" in n for n in notices)
    assert any("was ignored" in n for n in notices)


# ── Item 7: slug-collision guard through the routes (playtest F4) ────

SESSION_F4 = "77777777-8888-4999-8aaa-bbbbbbbbbbbb"
PC_NON_ASCII = "Þóra Björnsdóttir"
COLLIDER = "Ra Bj Rnsd Ttir"


def test_slug_collision_never_reaches_disk_or_display(
    client, fake_openai, fake_dispatch_log, tmp_data_dir
):
    """THE F4 REGRESSION: the collider slugs onto the PC's file and — as 'the
    PC's own write' under target-path authorization — renamed and clobbered
    the PC into a chimera. Now: op dropped, hint entry dropped, notice."""
    session_dir = tmp_data_dir / "state" / "core" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{SESSION_F4}.json").write_text(
        json.dumps(
            {
                "session_id": SESSION_F4,
                "world_name": "Röstigraben",
                "started_at": "2026-09-11T00:00:00Z",
                "turns": [],
                "active": True,
                "player_character_name": PC_NON_ASCII,
                "world_id": "7c0ffee0-0000-4000-8000-00000000000f",
            }
        ),
        encoding="utf-8",
    )
    block = json.dumps(
        {
            "characters": [
                {"name": PC_NON_ASCII, "action": "update", "status": "wounded"},
                {
                    "name": COLLIDER,
                    "action": "upsert",
                    "role": "player",  # bypass attempt rides along
                    "description": "a stranger who wears your face",
                },
            ]
        }
    )
    fake_openai.chat.completions.set_stream_tokens(
        ["A mirror cracks. ", f"<world_update>{block}</world_update>"]
    )

    response = client.post(
        "/api/stream", json={"action": "face them", "sessionId": SESSION_F4}
    )
    assert response.status_code == 200
    events = _events(response.text)

    # Write seam: exactly ONE op for the shared slug — the PC's own.
    entity_ops = [
        u
        for entry in fake_dispatch_log
        for u in entry["payload"]["updates"]
        if u["target_file"].endswith("/entities/ra_bj_rnsd_ttir.json")
    ]
    assert len(entity_ops) == 1
    assert entity_ops[0]["data"]["name"] == PC_NON_ASCII
    assert entity_ops[0]["data"]["status"] == "wounded"

    # Display seam: the collider is gone; the PC's entry survives.
    hint = next(e for e in events if e.get("type") == "world_update")["data"]
    names = [c.get("name") for c in hint["characters"]]
    assert COLLIDER not in names
    assert PC_NON_ASCII in names

    notices = [e["content"] for e in events if e.get("type") == "error"]
    assert any("collides" in n for n in notices)
