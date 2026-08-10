"""RFC-0019 / ADR-0004 Slice 1c — DM archetype mapping, engine-pinned.

A PC's ``class`` is free text ("Proctor", "chaingang boss"), so RFC-0018's derived
maxes failed safe for anyone not literally named after an archetype. The DM now
maps the class onto a top-level ``archetype`` slug at establishment, and the engine
pins it **write-once** — a later re-map would be a free HP lever (rogue ×6 →
warrior ×8).
"""

from engine import progression
from engine.class_rules import archetypes, canonical_archetype, resolve_class_rules
from engine.modules.registry import registry

ARCHETYPES = ("warrior", "rogue", "mage", "cleric")


def setup_function():
    registry.clear()


def teardown_function():
    registry.clear()


def _payload(ops):
    return {"session_id": "s", "log_entry": "x" * 10, "updates": ops}


def _op(**data):
    data.setdefault("name", "Sal")
    return {
        "target_file": "data/state/core/entities/sal.json",
        "operation": "update",
        "data": data,
    }


def _pc(**extra):
    pc = {
        "role": "player",
        "name": "Sal",
        "class": "Proctor",
        "level": 2,
        "module_data": {"character_sheet": {"stats": {"body": 6, "will": 5}}},
    }
    pc.update(extra)
    return pc


def _data(payload, idx=-1):
    return payload["updates"][idx]["data"]


def _enforce(payload, pc, **kw):
    kw.setdefault("class_rules", None)
    kw.setdefault("archetypes", ARCHETYPES)
    return progression.enforce_progression(
        payload,
        stored_characters=[pc],
        player_name="Sal",
        choice=None,
        **kw,
    )


# ── resolution: archetype wins, class is the fallback ─────────────────────────


def test_archetype_resolves_a_free_text_class():
    # The whole point: "Proctor" alone fails safe, but pinned to cleric it resolves.
    assert resolve_class_rules(None, {"class": "Proctor"}) is None
    assert resolve_class_rules(None, {"class": "Proctor", "archetype": "cleric"}) == {
        "hp_factor": 6,
        "magic": "divine",
    }


def test_archetype_wins_over_a_class_that_also_matches():
    pc = {"class": "Warrior", "archetype": "mage"}
    assert resolve_class_rules(None, pc)["hp_factor"] == 4  # mage, not warrior


def test_invalid_archetype_falls_back_to_class():
    pc = {"class": "Warrior", "archetype": "paladin"}
    assert resolve_class_rules(None, pc)["hp_factor"] == 8


def test_neither_resolves_is_none():
    assert (
        resolve_class_rules(None, {"class": "Proctor", "archetype": "paladin"}) is None
    )


def test_bare_string_still_treated_as_class():
    # Pre-RFC-0019 call shape keeps working.
    assert resolve_class_rules(None, "cleric")["hp_factor"] == 6


def test_archetypes_and_canonicalization():
    assert set(archetypes(None)) == set(ARCHETYPES)
    assert canonical_archetype(None, "CLERIC") == "cleric"
    assert canonical_archetype(None, "  Rogue ") == "rogue"
    assert canonical_archetype(None, "paladin") is None
    assert canonical_archetype(None, None) is None
    assert archetypes({"class": ""}) == ()  # no class module → inert


# ── the write-once pin ────────────────────────────────────────────────────────


def test_first_valid_archetype_is_accepted_and_canonicalized():
    payload = _payload([_op(archetype="Cleric")])
    _enforce(payload, _pc())
    assert _data(payload)["archetype"] == "cleric"  # stored lowercase


def test_invalid_archetype_is_dropped_not_stored():
    # Never persist a slug no rules-data can resolve — the PC stays unclassified so
    # the next turn can retry.
    payload = _payload([_op(archetype="paladin")])
    _enforce(payload, _pc())
    assert "archetype" not in _data(payload)


def test_stored_archetype_is_forced_over_a_dm_remap():
    # The attack: re-map rogue → warrior mid-session for Body×6 → Body×8 free HP.
    payload = _payload([_op(archetype="warrior")])
    notices = _enforce(payload, _pc(archetype="rogue"))
    assert _data(payload)["archetype"] == "rogue"
    assert any("archetype is set once" in n for n in notices)


def test_stored_archetype_forced_even_when_op_omits_it():
    # Every PC op carries it, so fs-manager's shallow merge can't drop it.
    payload = _payload([_op()])
    _enforce(payload, _pc(archetype="mage"))
    assert _data(payload)["archetype"] == "mage"


def test_matching_remap_is_not_flagged():
    payload = _payload([_op(archetype="ROGUE")])
    notices = _enforce(payload, _pc(archetype="rogue"))
    assert _data(payload)["archetype"] == "rogue"
    assert not any("archetype" in n for n in notices)


def test_garbage_stored_archetype_can_be_reestablished():
    # A legacy/garbage stored slug is treated as absent (self-healing), so a valid
    # DM value can take hold rather than being forced out forever.
    payload = _payload([_op(archetype="cleric")])
    _enforce(payload, _pc(archetype="paladin"))
    assert _data(payload)["archetype"] == "cleric"


def test_pin_is_inert_without_archetypes():
    # A world whose class module ships no rules-data behaves exactly as pre-RFC-0019.
    payload = _payload([_op(archetype="whatever")])
    _enforce(payload, _pc(archetype="rogue"), archetypes=())
    assert _data(payload)["archetype"] == "whatever"


def test_class_itself_is_never_touched():
    payload = _payload([_op(archetype="cleric")])
    _enforce(payload, _pc())
    assert "class" not in _data(payload)  # flavor untouched by the pin
