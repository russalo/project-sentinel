"""Tests for the subsystem-module infrastructure (ADR-0005 / RFC-0005,
RFC-0006).

Covers the manifest model, the loader + registry, and the DM-prompt
assembly. Two durable invariants:
  - migration integrity: the base module's fragment is still byte-
    identical to the pre-RFC-0005 ``DM_SYSTEM_PROMPT`` (frozen fixture);
  - assembly composition: the default prompt is the active modules'
    fragments composed in canonical order (base + character_sheet as of
    RFC-0006 Slice 1).
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


# ── Base-migration integrity + assembly composition ─────────────────


def test_base_fragment_byte_identical_to_pre_rfc0005():
    """The base module's prompt fragment must still equal the frozen
    pre-RFC-0005 DM_SYSTEM_PROMPT exactly — the RFC-0005 migration moved
    that content verbatim and nothing since should have altered it. (This
    is the durable migration-integrity check; build_dm_prompt() itself now
    composes more than base, so we check the base fragment directly.)"""
    frozen = _FIXTURE.read_text(encoding="utf-8")
    assert load_module("core/base-v1").prompt_fragment_text == frozen


def test_default_assembles_in_canonical_order():
    """RFC-0013: the default prompt is base + resolution + character_sheet
    + class + combat + magic + progression + time + tension, in
    CANONICAL_SUBSYSTEM_ORDER, joined by blank lines. Derives the
    expectation from the fragments themselves so it's not brittle to prose
    edits — pins the ORDER."""
    base = load_module("core/base-v1").prompt_fragment_text
    resolution = load_module("core/d100-open-v1").prompt_fragment_text
    sheet = load_module("core/four-stat-v1").prompt_fragment_text
    klass = load_module("core/four-class-fantasy-v1").prompt_fragment_text
    combat = load_module("core/hp-pool-v1").prompt_fragment_text
    magic = load_module("core/realm-pool-v1").prompt_fragment_text
    progression = load_module("core/milestone-v1").prompt_fragment_text
    time = load_module("core/time-cycle-v1").prompt_fragment_text
    tension = load_module("core/encounter-frames-v1").prompt_fragment_text
    assert build_dm_prompt() == (
        f"{base}\n\n{resolution}\n\n{sheet}\n\n{klass}\n\n{combat}\n\n{magic}"
        f"\n\n{progression}\n\n{time}\n\n{tension}"
    )


def test_dm_system_prompt_constant_matches_assembly():
    """The back-compat constant in engine.prompts.dm equals the assembled
    default prompt (the constant is defined as build_dm_prompt())."""
    from engine.prompts.dm import DM_SYSTEM_PROMPT

    assert DM_SYSTEM_PROMPT == build_dm_prompt()


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


def test_default_modules_is_nine_core_set():
    # RFC-0013: tension (encounter frames) joined — the Fantasy core ruleset
    # (resolution, sheet, classes, combat, magic, progression, time, tension)
    # on every world. Every reserved CANONICAL_SUBSYSTEM_ORDER slot is now
    # filled.
    assert DEFAULT_MODULES == {
        "base": "core/base-v1",
        "resolution": "core/d100-open-v1",
        "character_sheet": "core/four-stat-v1",
        "class": "core/four-class-fantasy-v1",
        "combat": "core/hp-pool-v1",
        "magic": "core/realm-pool-v1",
        "progression": "core/milestone-v1",
        "time": "core/time-cycle-v1",
        "tension": "core/encounter-frames-v1",
    }


def test_progression_module_loads():
    loaded = load_module("core/milestone-v1")
    assert loaded.manifest.subsystem == "progression"
    p = loaded.prompt_fragment_text
    assert "level_up" in p  # the proposal signal
    assert "LEVEL-UP CHOICE" in p  # the apply path
    # the PC-ownership wall: DM proposes, never decides
    assert "may NOT decide" in p or "player's to take" in p


def test_time_module_loads():
    loaded = load_module("core/time-cycle-v1")
    assert loaded.manifest.subsystem == "time"
    assert loaded.manifest.requires == (
        "core/four-stat-v1",
        "core/hp-pool-v1",
        "core/realm-pool-v1",
    )
    p = loaded.prompt_fragment_text
    # the bounded day cycle + the two rest kinds it teaches
    assert "timeOfDay" in p
    for token in ("SHORT REST", "LONG REST"):
        assert token in p
    # the boundary: rest does not revive the dead / bypass death saves
    assert "does NOT revive the dead" in p


def test_encounter_module_loads():
    loaded = load_module("core/encounter-frames-v1")
    assert loaded.manifest.subsystem == "tension"
    assert loaded.manifest.requires == (
        "core/four-stat-v1",
        "core/hp-pool-v1",
        "core/d100-open-v1",
    )
    p = loaded.prompt_fragment_text
    # the five-tier ladder + the persisted tier attribute
    for tier in ("trivial", "standard", "dangerous", "deadly", "mythic"):
        assert tier in p
    assert 'threat: "<tier>"' in p
    # surprise is check-gated; fleeing is a check at cost; consequences persist
    assert "REACTION CHECK" in p
    assert "AT COST" in p
    assert "didn't happen" in p  # the never-empty-resolution rule
    assert "DO NOT default to combat" in p


def test_magic_module_loads():
    loaded = load_module("core/realm-pool-v1")
    assert loaded.manifest.subsystem == "magic"
    assert loaded.manifest.schema_fragment == "schema.json"
    # bindings + the four deities + four traditions are taught inline
    for token in ("magic_pool", "The Mender", "Elementalist", "effect_die"):
        assert token in loaded.prompt_fragment_text


def test_resolution_module_loads():
    loaded = load_module("core/d100-open-v1")
    assert loaded.manifest.subsystem == "resolution"
    assert loaded.manifest.requires == ("core/four-stat-v1",)
    assert "check_request" in loaded.prompt_fragment_text
    assert "ROLL RESULT" in loaded.prompt_fragment_text


def test_class_module_loads():
    loaded = load_module("core/four-class-fantasy-v1")
    assert loaded.manifest.subsystem == "class"
    for cls in ("Warrior", "Rogue", "Mage", "Cleric"):
        assert cls in loaded.prompt_fragment_text


def test_combat_module_loads():
    loaded = load_module("core/hp-pool-v1")
    assert loaded.manifest.subsystem == "combat"
    assert loaded.manifest.requires == (
        "core/four-stat-v1",
        "core/four-class-fantasy-v1",
        "core/d100-open-v1",
    )
    assert "effect_die" in loaded.prompt_fragment_text
    assert "death save" in loaded.prompt_fragment_text.lower()


def test_character_sheet_module_loads():
    loaded = load_module("core/four-stat-v1")
    assert loaded.manifest.subsystem == "character_sheet"
    assert loaded.manifest.schema_fragment == "schema.json"
    assert "Body" in loaded.prompt_fragment_text
    assert "module_data" in loaded.prompt_fragment_text


def test_character_sheet_schema_fragment_is_valid_json_schema():
    # The declared schema fragment must parse as JSON + be a usable schema
    # (validates a good sheet, rejects an out-of-range stat). Enforcement
    # wiring is a later slice, but the authored contract must be sound now.
    import json as _json

    import jsonschema

    from engine.modules.loader import discover_modules as _discover

    manifest_path = _discover()["core/four-stat-v1"]
    schema_path = manifest_path.parent / "schema.json"
    schema = _json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    good = {"stats": {"body": 7, "mind": 5, "heart": 4, "will": 8}}
    assert list(validator.iter_errors(good)) == []
    bad = {"stats": {"body": 11, "mind": 5, "heart": 4, "will": 8}}
    assert list(validator.iter_errors(bad))  # body out of 1-10 range
    missing = {"stats": {"body": 7, "mind": 5, "heart": 4}}
    assert list(validator.iter_errors(missing))  # will required


def test_unknown_subsystem_key_is_ignored_not_crashed():
    # A modules map carrying a subsystem not in CANONICAL_SUBSYSTEM_ORDER
    # must not break assembly (forward-compat guard) — it's simply skipped.
    result = build_dm_prompt({"base": "core/base-v1", "made_up_subsystem": "x/y-v1"})
    assert result == build_dm_prompt()


def test_base_always_present_when_modules_omits_it():
    # A world that names some subsystems but omits `base` must still get the
    # invariant base prompt — DEFAULT_MODULES is layered under the override,
    # not replaced (codex P2 on PR #144). A world map that omits base but
    # map that omits it but names an unshipped subsystem still assembles to
    # the base prompt.
    result = build_dm_prompt({"made_up_subsystem": "x/y-v1"})
    assert result == build_dm_prompt()


def test_non_dict_modules_falls_back_to_default():
    # A malformed (non-dict) modules value must not crash assembly — it
    # falls back to the default set (gemini-medium on PR #144).
    default = build_dm_prompt()
    assert build_dm_prompt(["not", "a", "dict"]) == default
    assert build_dm_prompt("nonsense") == default
    assert build_dm_prompt(42) == default


def test_discovery_is_cached_on_registry():
    # discover_modules caches its scan on the registry so repeated calls
    # don't re-walk the tree (gemini-medium on PR #144).
    registry.clear()
    assert registry.get_discovery() is None
    first = discover_modules()
    assert registry.get_discovery() is not None
    second = discover_modules()
    assert first == second
    registry.clear()
    assert registry.get_discovery() is None
