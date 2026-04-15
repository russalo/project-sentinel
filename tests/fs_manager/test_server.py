"""Tests for ``mcp-servers/fs-manager/server.py``.

Covers the full security-gap closure landed with this PR:

- path validation rejects traversal and absolute paths
- protected-field enforcement runs on both ``create`` and ``update``
  (previously: only ``update``)
- protected-field list includes ``core_faction_id`` (previously
  missing from ``PROTECTED_FIELDS``)
- the per-update ``protected_check`` opt-out is gone entirely
  (previously: any payload could set ``protected_check: false``
  and bypass the protected-field check)
- payload-level namespace gate: writes to ``data/state/core/`` or
  ``data/lore/core/`` (excluding ``data/lore/core/sessions/``)
  require ``"namespace": "core"`` at the payload root (previously:
  no namespace check existed at all)
- session-log append at ``data/lore/core/sessions/<id>.md`` is
  exempt from the namespace gate so community callers can log
  their own sessions

Every test runs against a tmp ``REPO_ROOT`` supplied by the
``fs_manager_module`` fixture in ``conftest.py``.
"""

from __future__ import annotations

from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────


def _minimal_payload(
    *,
    session_id: str,
    target_file: str,
    operation: str = "create",
    data: dict | str | list | None = None,
    namespace: str | None = None,
) -> dict:
    """Build a minimally-valid apply_world_update payload.

    Only sets ``namespace`` when the caller explicitly provides one,
    so tests can distinguish "field absent" (defaults to community)
    from "field set to community" (explicit) from "field set to core".
    """
    if data is None:
        data = {"name": "Test", "status": "alive"}
    payload = {
        "session_id": session_id,
        "log_entry": "Test log entry for the fs-manager unit tests.",
        "updates": [
            {
                "target_file": target_file,
                "operation": operation,
                "data": data,
            }
        ],
    }
    if namespace is not None:
        payload["namespace"] = namespace
    return payload


# ── Path validation ──────────────────────────────────────────────────


def test_health_endpoint_responds_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_path_validation_rejects_directory_traversal(client, session_uuid):
    # Schema-level pattern rejection catches this before reaching
    # validate_path — the regex in apply_world_update.schema.json
    # doesn't match path components containing "..". That's fine;
    # 422 VALIDATION_ERROR and 403 PATH_VIOLATION are both acceptable
    # rejections, as long as the write doesn't land.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/../../../etc/passwd.json",
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code in (403, 422)


def test_path_validation_rejects_absolute_path(client, session_uuid):
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="/etc/passwd.json",
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code in (403, 422)


def test_path_validation_rejects_path_outside_data(client, session_uuid):
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="README.md",
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code in (403, 422)


# ── Protected-field enforcement ──────────────────────────────────────


def test_protected_field_blocks_update_with_world_seed(client, session_uuid, tmp_path):
    # Prepare an existing file so update is meaningful
    entity_path = tmp_path / "data" / "state" / "core" / "entities" / "kael.json"
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    entity_path.write_text('{"name": "Kael", "status": "alive"}')

    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/kael.json",
        operation="update",
        data={"world_seed": "attacker-controlled-seed"},
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


def test_protected_field_blocks_create_with_world_seed(client, session_uuid):
    # This is the regression test for the create-path bypass: the
    # previous code only ran check_protected_fields on the update
    # branch, so a malicious create could introduce a new file
    # containing arbitrary protected fields.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/new_entity.json",
        operation="create",
        data={"name": "NewEntity", "world_seed": "attacker-seed"},
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


def test_protected_field_list_includes_core_faction_id(client, session_uuid, tmp_path):
    # Regression test for the missing `core_faction_id` entry in
    # PROTECTED_FIELDS. ARCHITECTURE.md §4 listed it as protected;
    # the set did not include it until this PR.
    faction_path = tmp_path / "data" / "state" / "core" / "factions" / "shadow_court.json"
    faction_path.parent.mkdir(parents=True, exist_ok=True)
    faction_path.write_text('{"name": "Shadow Court", "relation": 0}')

    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/factions/shadow_court.json",
        operation="update",
        data={"core_faction_id": "different-faction-id"},
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


def test_protected_check_opt_out_is_rejected_by_schema(client, session_uuid):
    # Regression test for the `protected_check: false` bypass.
    # Before this PR the schema allowed per-update `protected_check`
    # as an optional boolean and the server honored it, letting any
    # caller turn off protection. The field is now gone from the
    # schema; including it fails validation with additionalProperties: false.
    payload = {
        "session_id": session_uuid,
        "log_entry": "Attempt to bypass protected-field enforcement.",
        "namespace": "core",
        "updates": [
            {
                "target_file": "data/state/core/entities/kael.json",
                "operation": "create",
                "data": {"name": "Kael", "world_seed": "attacker-seed"},
                "protected_check": False,
            }
        ],
    }
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── Namespace gate ───────────────────────────────────────────────────


def test_namespace_gate_blocks_community_default_core_write(client, session_uuid):
    # Payload omits `namespace` → defaults to community.
    # Target is under data/state/core/ → must be blocked.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/injection.json",
        operation="create",
        data={"name": "Injection"},
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NAMESPACE_VIOLATION"


def test_namespace_gate_blocks_explicit_community_core_write(client, session_uuid):
    # Uses the same target as the "default community" test above but
    # with `namespace` explicitly set to "community". Both the default
    # (omitted) and the explicit case must reach the namespace gate
    # and get rejected — no "explicit community is a magic token that
    # bypasses protection" footgun. The target is a data/state/core/
    # path because that's the only namespace-gated path class that
    # ALLOWED_PATH_PATTERN also permits at the schema layer
    # (data/lore/core/ writes are schema-rejected for everything
    # except sessions/, which is gate-exempt, so the gate would never
    # fire on a lore/core path in the current design).
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/injection.json",
        operation="create",
        data={"name": "Injection"},
        namespace="community",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NAMESPACE_VIOLATION"


def test_namespace_gate_allows_core_payload_to_write_core(
    client, session_uuid, tmp_path
):
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/kael.json",
        operation="create",
        data={"name": "Kael", "status": "alive"},
        namespace="core",
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 200
    assert (tmp_path / "data" / "state" / "core" / "entities" / "kael.json").exists()


def test_namespace_gate_allows_community_payload_to_write_community(
    client, session_uuid, tmp_path
):
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/community/bard_pack/npcs.json",
        operation="create",
        data={"npcs": ["Old Maren"]},
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 200
    written = tmp_path / "data" / "state" / "community" / "bard_pack" / "npcs.json"
    assert written.exists()


def test_session_log_exempt_from_namespace_gate_for_community_payload(
    client, session_uuid, tmp_path
):
    # The session log side-effect appends to data/lore/core/sessions/<id>.md
    # unconditionally. Community payloads must still be able to produce
    # that side effect or they can't log their own play sessions. The
    # CORE_GATED_PATH_PATTERN's `(?!sessions/)` negative lookahead
    # encodes this exemption.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/community/bard_pack/npcs.json",
        operation="create",
        data={"npcs": ["Old Maren"]},
    )
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 200

    session_log = tmp_path / "data" / "lore" / "core" / "sessions" / f"{session_uuid}.md"
    assert session_log.exists()
    assert "Test log entry" in session_log.read_text()


# ── Schema validation still catches top-level malformation ───────────


def test_schema_validation_rejects_missing_session_id(client):
    payload = {
        "log_entry": "Missing session_id means schema validation should fail.",
        "updates": [
            {
                "target_file": "data/state/core/entities/x.json",
                "operation": "create",
                "data": {"name": "X"},
            }
        ],
    }
    response = client.post("/tools/apply_world_update", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
