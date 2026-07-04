"""RFC-0016 — the mock-DM deploy-smoke fixture and client.

Two properties matter and are self-contained (no running backend needed):

1. Every fixture turn's ``<world_update>`` block, rendered exactly as the mock
   client emits it, survives the REAL ``engine.agents.fact_extractor.extract``
   with no errors and a schema-valid payload — i.e. the fixture would dispatch
   cleanly through the live turn loop.
2. ``backend.mock_dm`` returns the correct scripted output per turn (blocking and
   streaming) and refuses to over-run the script.

Plus a few arc assertions so a well-meaning edit can't silently break the
mechanics walkthrough (create -> combat to 0 HP -> unconscious -> death chain).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend import mock_dm
from engine.agents import fact_extractor

_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def settings():
    # mock_dm reads only ``dm_mock_fixture`` (None -> the committed default).
    return SimpleNamespace(dm_mock_fixture=None)


@pytest.fixture
def turns(settings):
    return mock_dm.load_turns(settings)


def test_fixture_has_a_contiguous_turn_run(turns):
    keys = sorted(turns)
    assert keys[0] == 0, "fixture must start at the intro (turn 0)"
    assert keys == list(range(keys[0], keys[-1] + 1)), "turn numbers must be contiguous"


def test_every_world_update_survives_the_real_extractor(settings, turns):
    """Render each turn as the mock emits it and run it through fact_extractor.

    ``check_request`` is a documented DM-emit key that lives INSIDE the
    ``<world_update>`` block (resolution/d100-open-v1 prompt) — the extractor
    doesn't dispatch it and notes it as an "unknown top-level key", but
    ``stream.py`` never reads ``extracted.errors`` (it surfaces check_request to
    the frontend via ``_parse_frontend_hint``), so that note is benign in
    production. We allow exactly that note and fail on any OTHER error.
    """
    for n in sorted(turns):
        raw = mock_dm._raw_for_turn(turns[n])
        result = fact_extractor.extract(raw, session_id=_UUID, turn_number=n)
        real_errors = [e for e in result.errors if "check_request" not in e]
        assert real_errors == [], (
            f"turn {n} produced non-benign extractor errors: {real_errors}"
        )
        # Turns whose only state is a check_request (no characters/locations/world)
        # legitimately dispatch nothing -> payload is None. Turns that mutate state
        # must yield a schema-valid, non-empty payload.
        wu = turns[n].get("world_update") or {}
        dispatchable = any(
            k in wu for k in ("world", "characters", "locations", "factions", "items")
        )
        if dispatchable:
            assert result.payload is not None, f"turn {n} should dispatch a payload"
            assert result.payload["updates"], f"turn {n} payload has no updates"


def test_mock_client_returns_scripted_turn_blocking(settings, turns):
    n = 0
    client = mock_dm.client_for_turn(settings, n)
    content = client.chat.completions.create().choices[0].message.content
    assert turns[n]["narrative"] in content
    assert "<world_update>" in content
    # The block is valid JSON round-trippable back to the fixture's world_update.
    block = content.split("<world_update>")[1].split("</world_update>")[0].strip()
    assert json.loads(block) == turns[n]["world_update"]


def test_mock_client_streaming_reconstructs_the_same_text(settings):
    client = mock_dm.client_for_turn(settings, 4)
    stream = client.chat.completions.create(stream=True)
    joined = "".join(chunk.choices[0].delta.content for chunk in stream)
    blocking = mock_dm.client_for_turn(settings, 4).chat.completions.create()
    assert joined == blocking.choices[0].message.content


def test_mock_client_refuses_to_overrun_the_script(settings, turns):
    over = max(turns) + 1
    with pytest.raises(KeyError):
        mock_dm.client_for_turn(settings, over)


def test_arc_create_to_death(turns):
    # T0 creates the Warrior PC at full HP, alive.
    pc0 = turns[0]["world_update"]["characters"][0]
    assert pc0["name"] == "Kaelen"
    hp0 = pc0["module_data"]["character_sheet"]["hp"]
    assert hp0["current"] == hp0["max"] == 56
    assert pc0["status"] == "alive"

    # HP decrements monotonically to 0 across the combat turns.
    hps = []
    for n in sorted(turns):
        for c in (turns[n]["world_update"] or {}).get("characters", []) or []:
            if c.get("name") == "Kaelen":
                hp = c.get("module_data", {}).get("character_sheet", {}).get("hp")
                if hp is not None:
                    hps.append(hp["current"])
    assert hps == sorted(hps, reverse=True), f"PC HP must not go up: {hps}"
    assert hps[-1] == 0, "PC must reach 0 HP"

    # Exactly one turn takes the PC unconscious at 0 HP.
    unconscious = [
        n
        for n in turns
        for c in (turns[n]["world_update"] or {}).get("characters", []) or []
        if c.get("name") == "Kaelen" and c.get("status") == "unconscious"
    ]
    assert len(unconscious) == 1

    # A 3-save death chain: three death_save check_requests are emitted.
    death_saves = [
        n
        for n in turns
        if ((turns[n]["world_update"] or {}).get("check_request") or {}).get("kind")
        == "death_save"
    ]
    assert len(death_saves) == 3, f"expected a 3-save death chain, got {death_saves}"

    # The terminal turn emits no further check_request (the run is over).
    assert (turns[max(turns)]["world_update"] or {}).get("check_request") is None


def test_pc_updates_carry_the_full_sheet(turns):
    """fs-manager's `operation: update` is a shallow top-level merge, so a Kaelen
    entry that emits only hp would ERASE stats.will + combat — breaking the
    death-save resolve (which reads the stored Will). Every PC update that touches
    the character_sheet must therefore re-emit the full sheet (stats + hp).
    """
    for n in sorted(turns):
        for c in (turns[n]["world_update"] or {}).get("characters", []) or []:
            if c.get("name") != "Kaelen":
                continue
            sheet = c.get("module_data", {}).get("character_sheet")
            if sheet is None:
                continue  # a pure status/location update that doesn't touch the sheet
            assert "stats" in sheet and sheet["stats"].get("will") == 4, (
                f"turn {n}: Kaelen sheet update dropped stats.will "
                f"(shallow merge would erase it before the death chain)"
            )
