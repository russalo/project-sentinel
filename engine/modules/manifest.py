"""Module manifest model + parser (ADR-0005 / RFC-0005).

A module is declared by a TOML manifest. Core modules live under
``engine/modules/<subsystem>/<impl>/manifest.toml`` and ship with the
engine code (they are trusted — a future module may carry Python
contract logic). Community modules live under
``data/lore/community/<pack>/modules/<slug>/manifest.toml`` and are
DATA-ONLY (TOML + Markdown + presets; no Python — the trusted/untrusted
boundary). RFC-0005 ships + loads core modules only.

The manifest is parsed with stdlib ``tomllib`` into a frozen dataclass
(the engine is pydantic-free — see ``engine/requirements.txt``).
Validation is explicit: a malformed manifest raises ``ManifestError``
with a path-tagged message rather than silently producing a half-formed
module.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ManifestError(ValueError):
    """A module manifest is missing a required field, has a wrong type,
    or otherwise fails validation. Carries enough context (the manifest
    path + the offending field) to locate the problem."""


# Module name format: "<namespace>/<slug>-v<major>" — e.g. "core/base-v1".
# namespace is "core" or "community/<pack>"; the slug is kebab-case; the
# trailing "-v<major>" pins the interface-compatible major line.
_NAME_OK_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/")


@dataclass(frozen=True)
class ModuleManifest:
    """In-memory representation of a module's manifest TOML.

    Fields:
        name              "<namespace>/<slug>-v<major>" (e.g. "core/base-v1")
        version           semantic-ish version string (e.g. "1.0.0")
        subsystem         which subsystem slot this module fills
        interface_version which subsystem-contract version it implements
        prompt_fragment   path to the DM-prompt contribution (.md),
                          RELATIVE to the manifest's own directory; None
                          if the module contributes no prompt text
        schema_fragment   path to the module's schema contribution (JSON
                          Schema), relative to the manifest dir; None for
                          modules that add no module_data fields
        preset_paths      glob patterns (relative to data_dir) the module's
                          content loader scans; empty for modules with no
                          authored content
        requires          other module names this module depends on
    """

    name: str
    version: str
    subsystem: str
    interface_version: str
    prompt_fragment: str | None = None
    schema_fragment: str | None = None
    preset_paths: tuple[str, ...] = field(default_factory=tuple)
    requires: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_toml_file(cls, path: Path) -> ModuleManifest:
        """Parse + validate a manifest TOML. Raises ManifestError on any
        missing/ill-typed required field."""
        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ManifestError(f"{path}: cannot read manifest: {exc}") from exc

        def _require_str(key: str) -> str:
            value = raw.get(key)
            if not isinstance(value, str) or not value:
                raise ManifestError(
                    f"{path}: manifest field {key!r} must be a non-empty string"
                )
            return value

        def _optional_str(key: str) -> str | None:
            value = raw.get(key)
            if value is None or value == "":
                return None
            if not isinstance(value, str):
                raise ManifestError(
                    f"{path}: manifest field {key!r} must be a string if present"
                )
            return value

        def _optional_str_list(key: str) -> tuple[str, ...]:
            value = raw.get(key, [])
            if not isinstance(value, list) or not all(
                isinstance(v, str) for v in value
            ):
                raise ManifestError(
                    f"{path}: manifest field {key!r} must be a list of strings"
                )
            return tuple(value)

        name = _require_str("name")
        if not set(name) <= _NAME_OK_CHARS or "/" not in name:
            raise ManifestError(
                f"{path}: manifest 'name' {name!r} must be "
                f"'<namespace>/<slug>-v<major>' (kebab-case, one slash)"
            )

        return cls(
            name=name,
            version=_require_str("version"),
            subsystem=_require_str("subsystem"),
            interface_version=_require_str("interface_version"),
            prompt_fragment=_optional_str("prompt_fragment"),
            schema_fragment=_optional_str("schema_fragment"),
            preset_paths=_optional_str_list("preset_paths"),
            requires=_optional_str_list("requires"),
        )
