"""RFC-0018 — resolving a world's class-module rules-data for a PC's class.

``resolve_class_rules`` is the IO boundary between a world's bound class module
and the pure ``engine.progression`` max computation. Its contract is fail-safe:
any miss returns None so the caller leaves the derived maxes DM-authored.
"""

from engine.class_rules import resolve_class_rules
from engine.modules.registry import registry


def setup_function():
    registry.clear()


def teardown_function():
    registry.clear()


def test_resolves_known_archetype_default_world():
    # modules=None → the default module set (which binds four-class-fantasy).
    assert resolve_class_rules(None, "Warrior") == {"hp_factor": 8, "magic": None}


def test_lookup_is_case_insensitive():
    assert resolve_class_rules(None, "mage")["hp_factor"] == 4
    assert resolve_class_rules(None, "MAGE")["hp_factor"] == 4
    assert resolve_class_rules(None, "  Cleric  ")["magic"] == "divine"


def test_free_text_class_misses_fail_safe():
    # The real-world free-text classes that motivated the fail-safe.
    assert resolve_class_rules(None, "Proctor") is None
    assert resolve_class_rules(None, "chaingang boss") is None


def test_non_string_or_empty_class_is_none():
    assert resolve_class_rules(None, None) is None
    assert resolve_class_rules(None, "") is None
    assert resolve_class_rules(None, "   ") is None
    assert resolve_class_rules(None, 7) is None


def test_world_can_clear_class_subsystem():
    # An explicit empty override clears the class slot → no module → None.
    assert resolve_class_rules({"class": ""}, "Warrior") is None


def test_class_module_without_rules_data_is_none():
    # A world bound to a class module that ships no rules-data (base has none)
    # fails safe rather than raising.
    assert resolve_class_rules({"class": "core/base-v1"}, "Warrior") is None


def test_unknown_class_module_is_none():
    assert resolve_class_rules({"class": "core/does-not-exist-v1"}, "Warrior") is None


# ── RFC-0019 ─────────────────────────────────────────────────────────────────


def test_non_dict_rules_entries_are_not_archetypes(monkeypatch):
    # coderabbit: a scalar metadata key must not be pinnable as an archetype that
    # resolve_class_rules could never resolve.
    from engine.modules import loader

    registry.clear()
    real = loader.load_module

    def fake(name):
        mod = real(name)
        if mod.rules_data is not None:
            object.__setattr__(
                mod, "rules_data", {**mod.rules_data, "schema": "1", "notes": None}
            )
        return mod

    monkeypatch.setattr("engine.class_rules.load_module", fake)
    from engine.class_rules import archetypes, canonical_archetype

    assert "schema" not in archetypes(None)
    assert canonical_archetype(None, "schema") is None
    assert canonical_archetype(None, "warrior") == "warrior"


def test_sanitize_payload_archetypes_drops_invalid():
    from engine.class_rules import sanitize_payload_archetypes

    payload = {
        "updates": [
            {
                "target_file": "data/state/core/entities/a.json",
                "operation": "update",
                "data": {"name": "A", "archetype": "paladin"},
            },
            {
                "target_file": "data/state/core/entities/b.json",
                "operation": "update",
                "data": {"name": "B", "archetype": "Cleric"},
            },
            {
                "target_file": "data/state/core/locations/c.json",
                "operation": "update",
                "data": {"name": "C", "archetype": "paladin"},
            },
        ]
    }
    assert sanitize_payload_archetypes(payload) == 1
    ops = payload["updates"]
    assert "archetype" not in ops[0]["data"]  # invalid dropped
    assert ops[1]["data"]["archetype"] == "cleric"  # canonicalized
    assert ops[2]["data"]["archetype"] == "paladin"  # non-entity op untouched


def test_sanitize_tolerates_malformed_payloads():
    from engine.class_rules import sanitize_payload_archetypes

    assert sanitize_payload_archetypes(None) == 0
    assert sanitize_payload_archetypes({}) == 0
    assert sanitize_payload_archetypes({"updates": "oops"}) == 0
    assert sanitize_payload_archetypes({"updates": [None, {"data": None}]}) == 0
