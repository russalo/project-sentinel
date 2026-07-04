"""RFC-0016 — mock-DM mode drives a real /api/stream turn end-to-end.

Proves the wiring: with ``settings.dm_mode == "mock"``, ``stream.py`` injects the
fixture client (not the live LLM / the conftest fake), so the SSE carries the
fixture's scripted narrative + its ``check_request``. Dispatch is the conftest
stub, so this exercises the turn loop without a real fs-manager.
"""

from __future__ import annotations

import dataclasses
import json

from tests.backend.test_stream import _parse_sse_events, _prime_session

_SESSION = "7c0ffee0-0000-4000-8000-000000000000"


def _mock_mode(app, test_settings):
    # Settings is frozen; swap in a mock-mode copy (default fixture).
    app.state.settings = dataclasses.replace(test_settings, dm_mode="mock")


def test_stream_turn_1_replays_the_fixture_skill_check(app, client, test_settings):
    _mock_mode(app, test_settings)
    # Empty turn history -> next_turn_number == 1 -> the fixture's skill-check turn.
    _prime_session(test_settings.data_dir, _SESSION, turns=[])

    resp = client.post("/api/stream", json={"action": "look at the runes", "sessionId": _SESSION})
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    # The scripted turn-1 narrative streamed as tokens.
    narrative = "".join(
        e["content"] for e in events if isinstance(e, dict) and e.get("type") == "token"
    )
    assert "crouch to read the worn glyphs" in narrative

    # The turn-1 check_request surfaced on the world_update event.
    wu = [e for e in events if isinstance(e, dict) and e.get("type") == "world_update"]
    assert wu, "expected a world_update SSE event"
    check = wu[-1]["data"].get("check_request")
    assert check is not None and check["stat"] == "mind" and check["target"] == 60


def test_stream_turn_number_selects_the_matching_fixture_turn(app, client, test_settings):
    _mock_mode(app, test_settings)
    # Prime one prior turn -> next_turn_number == 2 -> the fixture's resolve turn
    # (no check_request; it moves the player into the darkening wood).
    _prime_session(
        test_settings.data_dir,
        _SESSION,
        turns=[{"turn_number": 1, "playerAction": "x", "narrative": "y"}],
    )

    resp = client.post(
        "/api/stream",
        json={
            "action": "read on",
            "sessionId": _SESSION,
            "roll": {
                "kind": "skill",
                "stat": "mind",
                "rolled": 55,
                "bonus": 25,
                "total": 80,
                "target": 60,
                "margin": 20,
            },
        },
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    narrative = "".join(
        e["content"] for e in events if isinstance(e, dict) and e.get("type") == "token"
    )
    assert "Gravemaw" in narrative  # turn 2's scripted narrative
