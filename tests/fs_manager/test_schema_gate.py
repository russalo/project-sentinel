"""Red-team #1 regressions — schema-gate + fs-manager write-boundary hardening.

Covers the four breaks (all reachable via a DM-emitted <world_update>, or a
direct-MCP/migration caller that bypasses the schema):
  #1a string/scalar `data` on a `.json` target (bricks the file),
  #1b `append` to a `.json` target (corrupts it),
  #1c control/RTL/zero-width bytes in log_entry / append data,
  #1d case-variant protected-field keys writing through.

The schema is the primary gate (exercised via the endpoint); `execute_update`
carries a belt-and-suspenders copy for callers that never hit `validate_payload`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

SID = "3f0c1e2d-4a5b-4c6d-8e9f-0a1b2c3d4e5f"
JSON = "data/state/core/entities/kael.json"
MD = "data/lore/core/sessions/session.md"
RTL = chr(0x202E)  # right-to-left override
NUL = chr(0x00)


def _payload(target_file, operation, data, log_entry="A valid log entry for the test."):
    return {
        "session_id": SID,
        "log_entry": log_entry,
        "updates": [{"target_file": target_file, "operation": operation, "data": data}],
    }


def _apply(client, payload, namespace="core"):
    return client.post(
        "/tools/apply_world_update", json=payload, params={"namespace": namespace}
    )


# ── Schema gate (via the endpoint → validate_payload) ─────────────────────────


def test_schema_rejects_string_data_to_json(client):
    # #1a — a scalar written to a .json target would str(data) and brick it.
    r = _apply(client, _payload(JSON, "update", "oops-not-json"))
    assert r.status_code in (400, 422), r.text


def test_schema_allows_array_data_to_json(client):
    # arrays ARE valid state (the schema/coupling only rejects scalars).
    r = _apply(client, _payload(JSON, "create", [{"turn": 1}]))
    assert r.status_code == 200, r.text


def test_schema_rejects_append_to_json(client):
    # #1b — append to a .json target corrupts it.
    r = _apply(client, _payload(JSON, "append", "x"))
    assert r.status_code in (400, 422), r.text


def test_schema_rejects_control_bytes_in_log_entry(client):
    # #1c — an RTL override in log_entry corrupts the operator-facing transcript.
    r = _apply(
        client,
        _payload(
            JSON, "create", {"name": "K"}, log_entry="bad " + RTL + " reversed text"
        ),
    )
    assert r.status_code in (400, 422), r.text


def test_schema_rejects_control_bytes_in_append_data(client):
    r = _apply(client, _payload(MD, "append", "a line" + NUL + "with nul"))
    assert r.status_code in (400, 422), r.text


# ── Case-fold protected field (#1d, via the endpoint) ─────────────────────────


def test_protected_field_case_variant_blocked(client):
    r = _apply(
        client, _payload(JSON, "create", {"Unique_Id": "attacker", "WORLD_SEED": 7})
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


# ── fs-manager belt-and-suspenders (direct execute_update, bypasses the schema) ─


def test_execute_update_rejects_scalar_to_json(fs_manager_module):
    with pytest.raises(HTTPException) as exc:
        fs_manager_module.execute_update(JSON, "update", "scalar")
    assert exc.value.status_code == 422


def test_execute_update_rejects_append_to_non_md(fs_manager_module):
    with pytest.raises(HTTPException) as exc:
        fs_manager_module.execute_update(JSON, "append", "x")
    assert exc.value.status_code == 422


def test_execute_update_corrupted_json_returns_structured_500(fs_manager_module):
    # A pre-existing corrupted state file must degrade to a structured 500, not a
    # bare 500 from an uncaught JSONDecodeError (#1a).
    root = fs_manager_module.REPO_ROOT
    p = root / JSON
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        fs_manager_module.execute_update(JSON, "update", {"name": "K"})
    assert exc.value.status_code == 500
    assert exc.value.detail["code"] == "CORRUPTED_STATE"


def test_execute_update_scrubs_control_bytes_in_append(fs_manager_module):
    root = fs_manager_module.REPO_ROOT
    fs_manager_module.execute_update(MD, "append", "clean" + RTL + NUL + "text")
    written = (root / MD).read_text(encoding="utf-8")
    assert RTL not in written and NUL not in written
    assert "cleantext" in written


def test_execute_update_scrubs_control_bytes_in_create_md(fs_manager_module):
    # Sibling-path gap (review of #1c): create/update of a .md target with a
    # control-byte string is scrubbed too, not only append.
    root = fs_manager_module.REPO_ROOT
    fs_manager_module.execute_update(MD, "create", "clean" + RTL + NUL + "text")
    written = (root / MD).read_text(encoding="utf-8")
    assert RTL not in written and NUL not in written and "cleantext" in written


def test_scrub_control_bytes_keeps_tab_and_newline(fs_manager_module):
    scrub = fs_manager_module.scrub_control_bytes
    assert scrub("a" + RTL + "b" + NUL + "c") == "abc"
    assert scrub("line1\n\tline2") == "line1\n\tline2"  # tab/newline preserved
