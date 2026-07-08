"""Red-team #1c review (codex) — a log_entry built from user/DM text is scrubbed
before it reaches the tightened schema.

`_build_session_payload` is the single chokepoint for every session-file write
(session start uses `body.world_name`, a turn uses the DM narrative, reauth uses
`username`). The schema now rejects control bytes in `log_entry`, so without a
scrub a world named with an RTL override would 502 session creation.
"""

from backend.state.sessions import Session, _build_session_payload
from engine.schema import validate

RTL = chr(0x202E)  # right-to-left override
NUL = chr(0x00)


def _session():
    return Session(
        session_id="3f0c1e2d-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
        world_name="Testworld",
        started_at="2026-01-01T00:00:00Z",
    )


def test_build_session_payload_scrubs_control_bytes_in_log_entry():
    payload = _build_session_payload(
        _session(),
        log_entry="[Session Start] Bad" + RTL + NUL + "Name — intro generated.",
        turn_number=0,
    )
    le = payload["log_entry"]
    assert RTL not in le and NUL not in le
    assert "BadName" in le


def test_scrubbed_session_payload_passes_the_tightened_schema():
    # The regression codex flagged: a control-byte log_entry, once scrubbed, must
    # validate — otherwise session creation / turn writes 502 on stray bytes.
    payload = _build_session_payload(
        _session(),
        log_entry="A world named X" + RTL + " opens to the player here.",
        turn_number=0,
    )
    assert validate(payload).ok, payload["log_entry"]
