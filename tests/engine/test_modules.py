"""Tests for the subsystem-module infrastructure (ADR-0005 / RFC-0005).

Covers the manifest model, the loader + registry, the DM-prompt
assembly, and the central safety property of RFC-0005: the assembled
prompt for the default (base-only) module set is byte-identical to the
pre-RFC-0005 ``DM_SYSTEM_PROMPT`` (frozen in a fixture).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.modules import (
    CANONICAL_SUBSYSTEM_ORDER,
    DEFAULT_MODULES,
    build_dm_prompt,
    discover_modules,
    load_module,
)
from engine.modules.manifest import ManifestError, ModuleManifest
from engine.modules.registry import registry

_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "dm_system_prompt_pre_rfc0005.txt"
)


@pytest.fixture(autouse=True)
def _cold_registry():
    """Each test starts with a cold module cache so loader behavior is
    exercised, not a warm cache from a prior test."""
    registry.clear()
    yield
    registry.clear()


# ── Equivalence: the central RFC-0005 safety property ───────────────


def test_default_prompt_is_byte_identical_to_pre_rfc0005():
    """build_dm_prompt() for the default module set must equal the frozen
    pre-RFC-0005 DM_SYSTEM_PROMPT exactly. If this fails, the base module
    migration changed prompt behavior — investigate, don't re-baseline."""
    frozen = _FIXTURE.read_text(encoding="utf-8")
    assert build_dm_prompt() == frozen


def test_dm_system_prompt_constant_matches_assembly():
    """The back-compat constant in engine.prompts.dm equals the assembled
    default prompt (the constant is defined as build_dm_prompt())."""
    from engine.prompts.dm import DM_SYSTEM_PROMPT

    assert DM_SYSTEM_PROMPT == build_dm_prompt()


def test_explicit_base_set_equals_default():
    assert build_dm_prompt({"base": "core/base-v1"}) == build_dm_prompt()


def test_none_and_empty_modules_fall_back_to_default():
    default = build_dm_prompt()
    assert build_dm_prompt(None) == default
    assert build_dm_prompt({}) == default


# ── Discovery + loading ─────────────────────────────────────────────


def test_discover_finds_base_module():
    found = discover_modules()
    assert "core/base-v1" in found
    assert found["core/base-v1"].name == "manifest.toml"


def test_load_base_module():
    loaded = load_module("core/base-v1")
    assert loaded.manifest.name == "core/base-v1"
    assert loaded.manifest.subsystem == "base"
    assert loaded.manifest.interface_version == "1.0"
    assert loaded.prompt_fragment_text  # non-empty
    # No trailing newline (loader rstrips so the .md can carry one).
    assert not loaded.prompt_fragment_text.endswith("\n")


def test_load_unknown_module_raises():
    with pytest.raises(ManifestError, match="unknown module"):
        load_module("core/does-not-exist-v1")


def test_registry_caches_loaded_module():
    first = load_module("core/base-v1")
    second = load_module("core/base-v1")
    assert first is second  # same cached object


# ── Manifest validation ─────────────────────────────────────────────


def test_manifest_parses_base(tmp_path: Path):
    found = discover_modules()
    manifest = ModuleManifest.from_toml_file(found["core/base-v1"])
    assert manifest.name == "core/base-v1"
    assert manifest.prompt_fragment == "prompt.md"
    assert manifest.preset_paths == ()
    assert manifest.requires == ()


def test_manifest_rejects_missing_required_field(tmp_path: Path):
    bad = tmp_path / "manifest.toml"
    bad.write_text('name = "core/x-v1"\nversion = "1.0.0"\n', encoding="utf-8")
    # missing subsystem + interface_version
    with pytest.raises(ManifestError, match="subsystem"):
        ModuleManifest.from_toml_file(bad)


def test_manifest_rejects_bad_name_format(tmp_path: Path):
    bad = tmp_path / "manifest.toml"
    bad.write_text(
        'name = "noslug"\nversion = "1.0.0"\nsubsystem = "base"\n'
        'interface_version = "1.0"\n',
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="name"):
        ModuleManifest.from_toml_file(bad)


def test_manifest_rejects_non_list_preset_paths(tmp_path: Path):
    bad = tmp_path / "manifest.toml"
    bad.write_text(
        'name = "core/x-v1"\nversion = "1.0.0"\nsubsystem = "base"\n'
        'interface_version = "1.0"\npreset_paths = "not-a-list"\n',
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="preset_paths"):
        ModuleManifest.from_toml_file(bad)


# ── Assembly ordering + forward-compat ──────────────────────────────


def test_base_is_first_in_canonical_order():
    assert CANONICAL_SUBSYSTEM_ORDER[0] == "base"


def test_default_modules_is_base_only():
    assert DEFAULT_MODULES == {"base": "core/base-v1"}


def test_unknown_subsystem_key_is_ignored_not_crashed():
    # A modules map carrying a subsystem not in CANONICAL_SUBSYSTEM_ORDER
    # must not break assembly (forward-compat guard) — it's simply skipped.
    result = build_dm_prompt({"base": "core/base-v1", "made_up_subsystem": "x/y-v1"})
    assert result == build_dm_prompt()
