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
- namespace gate: writes to ``data/state/core/`` or ``data/lore/core/``
  (excluding ``data/lore/core/sessions/``) require the trusted
  ``?namespace=core`` query param (PR 3 / red-team #7) — set by the backend on
  dispatch, NOT a field in the LLM-parsed body; passed here via ``_apply``
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
) -> dict:
    """Build a minimally-valid apply_world_update payload.

    ``namespace`` is NOT a body field (PR 3 / red-team #7) — it's the trusted
    query param the backend sets; pass it to ``_apply``, not here.
    """
    if data is None:
        data = {"name": "Test", "status": "alive"}
    return {
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


def _apply(client, payload, namespace=None):
    """POST a payload to apply_world_update, sending ``namespace`` as the trusted
    query param (PR 3). ``namespace=None`` sends no param → fs-manager defaults to
    the least-privileged "community" scope.
    """
    params = {"namespace": namespace} if namespace is not None else None
    return client.post("/tools/apply_world_update", json=payload, params=params)


def _count_files_under(root: Path) -> int:
    """Count every regular file under ``root`` recursively.

    Used by rejection tests to assert "the server didn't just return
    an error, it also didn't write anything." A test that only checks
    ``response.status_code == 403`` would silently pass if the server
    returned 403 AFTER partially writing to disk — the negative
    filesystem assertion catches that class of regression.
    """
    return sum(1 for p in root.rglob("*") if p.is_file())


# ── Path validation ──────────────────────────────────────────────────


def test_health_endpoint_responds_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_path_validation_rejects_directory_traversal(client, session_uuid, tmp_path):
    # Schema-level pattern rejection catches this before reaching
    # validate_path — the regex in apply_world_update.schema.json
    # doesn't match path components containing "..". That's fine;
    # 422 VALIDATION_ERROR and 403 PATH_VIOLATION are both acceptable
    # rejections, as long as the write doesn't land.
    files_before = _count_files_under(tmp_path)
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/../../../etc/passwd.json",
    )
    response = _apply(client, payload)
    assert response.status_code in (403, 422)
    # Security property: the rejected request must not have produced
    # any new files on disk — including a partial session log append.
    assert _count_files_under(tmp_path) == files_before


def test_path_validation_rejects_absolute_path(client, session_uuid, tmp_path):
    files_before = _count_files_under(tmp_path)
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="/etc/passwd.json",
    )
    response = _apply(client, payload)
    assert response.status_code in (403, 422)
    assert _count_files_under(tmp_path) == files_before


def test_path_validation_rejects_path_outside_data(client, session_uuid, tmp_path):
    files_before = _count_files_under(tmp_path)
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="README.md",
    )
    response = _apply(client, payload)
    assert response.status_code in (403, 422)
    assert _count_files_under(tmp_path) == files_before
    # Extra defense: the target itself should never land under tmp_path.
    assert not (tmp_path / "README.md").exists()


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
    )
    response = _apply(client, payload, namespace="core")
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
    )
    response = _apply(client, payload, namespace="core")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


def test_protected_field_list_includes_core_faction_id(client, session_uuid, tmp_path):
    # Regression test for the missing `core_faction_id` entry in
    # PROTECTED_FIELDS. ARCHITECTURE.md §4 listed it as protected;
    # the set did not include it until this PR.
    faction_path = (
        tmp_path / "data" / "state" / "core" / "factions" / "shadow_court.json"
    )
    faction_path.parent.mkdir(parents=True, exist_ok=True)
    faction_path.write_text('{"name": "Shadow Court", "relation": 0}')

    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/factions/shadow_court.json",
        operation="update",
        data={"core_faction_id": "different-faction-id"},
    )
    response = _apply(client, payload, namespace="core")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"


def test_protected_field_blocked_when_list_wrapped(client, session_uuid, tmp_path):
    # red-team #5: the schema permits `data` as an array, and the old check
    # returned early on any non-dict — so a list-wrapped payload smuggled
    # top-level protected fields past the guard and wrote them verbatim. The
    # check now inspects each list element's top-level keys.
    files_before = _count_files_under(tmp_path)
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/listwrap.json",
        operation="create",
        data=[{"name": "X", "world_seed": "attacker-seed"}],
    )
    response = _apply(client, payload, namespace="core")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROTECTED_FIELD_VIOLATION"
    assert _count_files_under(tmp_path) == files_before  # nothing written


def test_nested_protected_field_is_allowed(client, session_uuid):
    # codex P1 on #93: a protected field nested DEEPER than the top level is
    # stored as ordinary nested data (shallow merge / verbatim write), not a
    # mutation of the object's own protected field — so it must be ALLOWED.
    # Recursing into it would 403 every legitimate session write, whose turn
    # entries carry `created_at` nested in `data["turns"]` → 502 on new sessions.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file=f"data/state/core/sessions/{session_uuid}.json",
        operation="create",
        data={
            "session_id": session_uuid,
            "turns": [{"turn_number": 0, "created_at": "2026-06-05T00:00:00Z"}],
        },
    )
    response = _apply(client, payload, namespace="core")
    assert response.status_code == 200, response.text  # nested created_at allowed


def test_non_object_payload_returns_422_not_500(client, tmp_path):
    # red-team #2/#8: a non-dict top-level JSON body (array/string/number/null)
    # used to raise an uncaught AttributeError at the log line → bare 500 +
    # stack trace. It must now return the structured 422 envelope.
    files_before = _count_files_under(tmp_path)
    for body in ("[1,2,3]", '"x"', "42", "null"):
        response = client.post(
            "/tools/apply_world_update",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422, f"body={body}"
        assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert _count_files_under(tmp_path) == files_before


def test_invalid_json_body_returns_422(client, tmp_path):
    # Malformed JSON must also be a clean 422, not a 500 from request.json().
    response = client.post(
        "/tools/apply_world_update",
        content="{not valid json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_malformed_updates_field_returns_422(client, session_uuid):
    # gemini on #93: a dict payload whose `updates` isn't a list (null / int)
    # must be a clean schema 422, not a 500 — it passes the isinstance(dict)
    # guard but fails JSON-Schema validation (`updates` is `type: array`).
    for updates in (None, 5, "x"):
        payload = {
            "session_id": session_uuid,
            "log_entry": "x",
            "updates": updates,
        }
        response = _apply(client, payload)
        assert response.status_code == 422, f"updates={updates!r}"
        assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_protected_check_opt_out_is_rejected_by_schema(client, session_uuid):
    # Regression test for the `protected_check: false` bypass.
    # Before this PR the schema allowed per-update `protected_check`
    # as an optional boolean and the server honored it, letting any
    # caller turn off protection. The field is now gone from the
    # schema; including it fails validation with additionalProperties: false.
    payload = {
        "session_id": session_uuid,
        "log_entry": "Attempt to bypass protected-field enforcement.",
        "updates": [
            {
                "target_file": "data/state/core/entities/kael.json",
                "operation": "create",
                "data": {"name": "Kael", "world_seed": "attacker-seed"},
                "protected_check": False,
            }
        ],
    }
    response = _apply(client, payload)
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
    response = _apply(client, payload)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NAMESPACE_VIOLATION"


def test_namespace_gate_blocks_explicit_community_core_write(client, session_uuid):
    # Same target as the "default community" test above, but with the explicit
    # ?namespace=community query param. Both the default (omitted param) and the
    # explicit-community case must reach the namespace gate and get rejected — no
    # "explicit community is a magic token that bypasses protection" footgun. The
    # target is a data/state/core/ path because that's the only namespace-gated
    # path class ALLOWED_PATH_PATTERN also permits at the schema layer.
    payload = _minimal_payload(
        session_id=session_uuid,
        target_file="data/state/core/entities/injection.json",
        operation="create",
        data={"name": "Injection"},
    )
    response = _apply(client, payload, namespace="community")
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
    )
    response = _apply(client, payload, namespace="core")
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
    response = _apply(client, payload)
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
    response = _apply(client, payload)
    assert response.status_code == 200

    session_log = (
        tmp_path / "data" / "lore" / "core" / "sessions" / f"{session_uuid}.md"
    )
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
    response = _apply(client, payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── session_id format + traversal defense ───────────────────────────


def test_schema_validation_rejects_non_uuid_session_id(client, tmp_path):
    # jsonschema doesn't enforce `format` keywords unless you pass it
    # a FormatChecker. validate_payload now passes _FORMAT_CHECKER, so
    # a non-UUID session_id must be rejected at the schema layer —
    # before reaching the session-log append that would otherwise
    # interpolate it into a filesystem path.
    files_before = _count_files_under(tmp_path)
    payload = {
        "session_id": "not-a-uuid-string",
        "log_entry": "session_id is not a UUID and must be rejected.",
        "updates": [
            {
                "target_file": "data/state/core/entities/kael.json",
                "operation": "create",
                "data": {"name": "Kael", "status": "alive"},
            }
        ],
    }
    response = _apply(client, payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert _count_files_under(tmp_path) == files_before


def test_traversal_attempt_in_session_id_is_rejected(client, tmp_path):
    # Defense-in-depth belt test: even if someone crafts a string that
    # looks UUID-ish enough to slip past `format: uuid`, the session
    # log path resolution in _resolve_session_log_path() must catch
    # the traversal and refuse to open a file outside sessions/.
    #
    # This string won't actually pass the format check (jsonschema's
    # UUID validator is strict), but we exercise the code path by
    # checking that any rejection occurs and that no file lands
    # outside the sessions directory. This is the second layer of
    # defense — if format checking ever regresses, this test keeps
    # the filesystem boundary honest.
    files_before = _count_files_under(tmp_path)
    payload = {
        # Not a valid UUID; format check will fire first, but even
        # if it didn't, the path resolution would catch it.
        "session_id": "../../../etc/passwd",
        "log_entry": "Traversal attempt via session_id interpolation.",
        "updates": [
            {
                "target_file": "data/state/core/entities/kael.json",
                "operation": "create",
                "data": {"name": "Kael", "status": "alive"},
            }
        ],
    }
    response = _apply(client, payload)
    # Either layer of defense is acceptable — format check (422) or
    # path resolution (403 PATH_VIOLATION). Both are correct; the
    # critical property is that the file system is untouched.
    assert response.status_code in (403, 422)
    assert _count_files_under(tmp_path) == files_before
    # Explicitly: nothing landed anywhere named "passwd".
    assert not list(tmp_path.rglob("*passwd*"))
