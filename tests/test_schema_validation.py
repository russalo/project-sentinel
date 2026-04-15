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


# ── community_manifest schema tests ───────────────────────────────────────────


def test_valid_community_manifest_passes():
    """A correctly formed community pack manifest must validate without error."""
    payload = load_fixture("valid_community_manifest.json")
    _validate(payload, COMMUNITY_MANIFEST_SCHEMA)
