"""Red-team #1c review (codex) — log_entry is scrubbed of control/RTL/zero-width
bytes at the single dispatch chokepoint (`engine.apply_world_update`).

The tightened schema rejects control bytes in log_entry. log_entry is built from
user/DM text by several producers — session start (`body.world_name`), a turn
(the DM narrative), reauth (`username`), and the inline death-outcome payload in
stream.py (which bypasses the session-payload builder entirely). Scrubbing at the
one dispatch chokepoint covers all of them, so none can 502 the write on a stray
byte, and a future producer can't miss it.
"""

import json

import httpx

from engine import apply_world_update
from engine.types import Config

RTL = chr(0x202E)  # right-to-left override
NUL = chr(0x00)
ZWSP = chr(0x200B)  # zero-width space
SID = "3f0c1e2d-4a5b-4c6d-8e9f-0a1b2c3d4e5f"


def _config():
    return Config(openai_api_key="test-key", fs_manager_url="http://fs")


def _capture_client(captured):
    def handler(request):
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "ok"})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="")


def test_apply_world_update_scrubs_log_entry_at_dispatch():
    captured = {}
    payload = {
        "session_id": SID,
        "log_entry": "[Session Start] Bad" + RTL + NUL + ZWSP + "Name — intro.",
        "updates": [],
    }
    apply_world_update(_config(), payload, client=_capture_client(captured))
    sent = json.loads(captured["body"])["log_entry"]
    assert RTL not in sent and NUL not in sent and ZWSP not in sent
    assert "BadName" in sent


def test_apply_world_update_does_not_mutate_caller_payload():
    captured = {}
    original = "keep" + RTL + "clean and long enough"
    payload = {"session_id": SID, "log_entry": original, "updates": []}
    apply_world_update(_config(), payload, client=_capture_client(captured))
    # The caller's dict is untouched — a scrubbed copy is posted.
    assert payload["log_entry"] == original
    assert RTL not in json.loads(captured["body"])["log_entry"]
