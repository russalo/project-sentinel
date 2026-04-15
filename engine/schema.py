"""Schema loading and validation for apply_world_update payloads.

Loads ``schemas/apply_world_update.schema.json`` from the repo root and
exposes a single ``validate()`` entry point. Path resolution is relative
to this file, so the package works regardless of current working
directory.

Lazy loading
------------
The schema file is read on first call to ``validate()``, not at import
time. This keeps ``import engine`` side-effect-free (importing the
package does no filesystem I/O) and makes the module testable in
environments where the schema file is absent — the caller only pays
the load cost when they actually validate a payload.

Format checking
---------------
The validator is constructed with
``format_checker=jsonschema.FormatChecker()`` so that ``format``
constraints in the schema (e.g. ``session_id`` is ``format: uuid``) are
actually enforced. Without a format checker, jsonschema silently skips
all format validations, which would make this validator strictly less
strict than ``tests/test_schema_validation.py`` — a trap.

Schema path coupling
--------------------
``_SCHEMA_PATH`` currently assumes the repo layout
(``engine/../schemas/``). When ``engine/`` is later extracted into its
own installable package, this path will need to be revisited — either
by bundling the schema as package data via ``importlib.resources`` or
by having the caller inject the loaded schema. Tracked in
``docs/BACKLOG.md``.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import jsonschema
from jsonschema.validators import Draft202012Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "apply_world_update.schema.json"
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]


def load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(), format_checker=jsonschema.FormatChecker()
    )


def validate(payload: dict) -> ValidationResult:
    """Validate a payload against apply_world_update.schema.json.

    Returns ValidationResult(ok=True, errors=[]) on success, or
    ValidationResult(ok=False, errors=[...]) with human-readable
    error messages on failure.
    """
    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.path))
    if not errors:
        return ValidationResult(ok=True, errors=[])
    messages = [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    ]
    return ValidationResult(ok=False, errors=messages)
