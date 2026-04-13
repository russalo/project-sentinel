"""Schema loading and validation for apply_world_update payloads.

Loads schemas/apply_world_update.schema.json from the repo root and
exposes a single `validate()` entry point. Path resolution is relative
to this file, so the package works regardless of current working
directory.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema.validators import Draft202012Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "apply_world_update.schema.json"
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def load_schema() -> dict:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


_SCHEMA = load_schema()
_VALIDATOR = Draft202012Validator(_SCHEMA)


def validate(payload: dict) -> ValidationResult:
    """Validate a payload against apply_world_update.schema.json.

    Returns ValidationResult(ok=True, errors=[]) on success, or
    ValidationResult(ok=False, errors=[...]) with human-readable
    error messages on failure.
    """
    errors = sorted(_VALIDATOR.iter_errors(payload), key=lambda e: list(e.path))
    if not errors:
        return ValidationResult(ok=True, errors=[])
    messages = [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    ]
    return ValidationResult(ok=False, errors=messages)
