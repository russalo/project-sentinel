"""
Project Sentinel — Schema Validation Tests

Verifies that the JSON Schema contracts correctly accept valid payloads
and reject invalid ones. These tests run in CI on every push/PR and
serve as the automated proof that "the schema gate is the law."

Run locally:
    pip install jsonschema pytest
    pytest tests/test_schema_validation.py -v
"""

import json
from pathlib import Path

import jsonschema
import jsonschema.validators
import pytest

REPO_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


# Load schemas once at module level
WORLD_UPDATE_SCHEMA = load_schema("apply_world_update.schema.json")
COMMUNITY_MANIFEST_SCHEMA = load_schema("community_manifest.schema.json")


# ── apply_world_update schema tests ───────────────────────────────────────────


def _validate(instance: dict, schema: dict) -> None:
    """Validate with format checking enabled (enforces 'uuid', 'date-time', etc.)."""
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())
    validator.validate(instance)


def test_valid_world_update_passes():
    """A correctly formed world update payload must validate without error."""
    payload = load_fixture("valid_world_update.json")
    _validate(payload, WORLD_UPDATE_SCHEMA)


def test_missing_session_id_fails():
    """A payload missing the required session_id field must be rejected."""
    payload = load_fixture("invalid_missing_session.json")
    with pytest.raises(jsonschema.ValidationError):
        _validate(payload, WORLD_UPDATE_SCHEMA)


def test_path_traversal_fails():
    """A payload with a directory-traversal target_file must be rejected by the pattern constraint."""
    payload = load_fixture("invalid_path_traversal.json")
    with pytest.raises(jsonschema.ValidationError):
        _validate(payload, WORLD_UPDATE_SCHEMA)


# ── red-team #1: operation/extension/data-type coupling + control-byte guard ──

_SID = "3f0c1e2d-4a5b-4c6d-8e9f-0a1b2c3d4e5f"
_JSON = "data/state/core/entities/kael.json"
_MD = "data/lore/core/sessions/s.md"


def _wu(target_file, operation, data, log_entry="a valid ten-plus char entry"):
    return {
        "session_id": _SID,
        "log_entry": log_entry,
        "updates": [{"target_file": target_file, "operation": operation, "data": data}],
    }


def test_schema_rejects_scalar_data_on_json_target():
    # #1a — a string/scalar to a .json target would str(data) and brick the file.
    with pytest.raises(jsonschema.ValidationError):
        _validate(_wu(_JSON, "update", "oops"), WORLD_UPDATE_SCHEMA)


def test_schema_allows_array_data_on_json_target():
    _validate(_wu(_JSON, "update", [{"turn": 1}]), WORLD_UPDATE_SCHEMA)


def test_schema_rejects_append_to_json_target():
    # #1b — append is Markdown-only; append to .json corrupts state.
    with pytest.raises(jsonschema.ValidationError):
        _validate(_wu(_JSON, "append", "x"), WORLD_UPDATE_SCHEMA)


def test_schema_rejects_control_bytes_in_log_entry():
    # #1c — an RTL override (U+202E) in log_entry corrupts the transcript.
    with pytest.raises(jsonschema.ValidationError):
        _validate(
            _wu(_JSON, "update", {}, log_entry="bad " + chr(0x202E) + " text"),
            WORLD_UPDATE_SCHEMA,
        )


def test_schema_rejects_control_bytes_in_append_data():
    with pytest.raises(jsonschema.ValidationError):
        _validate(
            _wu(_MD, "append", "a line" + chr(0x00) + " nul"), WORLD_UPDATE_SCHEMA
        )


def test_schema_allows_clean_append_to_md_and_tab_newline():
    _validate(_wu(_MD, "append", "clean line\n\twith tab"), WORLD_UPDATE_SCHEMA)


def test_schema_rejects_control_bytes_in_create_md_string():
    # Sibling-path gap (review of #1c): a create/update writing a control-byte
    # STRING to a .md target must also be rejected, not only append.
    with pytest.raises(jsonschema.ValidationError):
        _validate(_wu(_MD, "create", "bad " + chr(0x202E) + " x"), WORLD_UPDATE_SCHEMA)


# ── community_manifest schema tests ───────────────────────────────────────────


def test_valid_community_manifest_passes():
    """A correctly formed community pack manifest must validate without error."""
    payload = load_fixture("valid_community_manifest.json")
    _validate(payload, COMMUNITY_MANIFEST_SCHEMA)
