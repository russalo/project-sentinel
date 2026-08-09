"""RFC-0017 — the SSE-hint mirror shows a committed level-up live (codex review).

The DM no longer writes `level`/`stats`, so without mirroring the engine-committed
values into the `world_update` hint the player wouldn't see the advance until a full
hydration.
"""

from backend.routes.stream import _mirror_progression_to_hint, _normalize_vitality_hint


def test_mirror_patches_existing_pc_entry():
    hint = {
        "characters": [
            {"name": "Kael", "role": "player", "level": 2, "status": "alive"}
        ]
    }
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8, "mind": 5})
    pc = hint["characters"][0]
    assert pc["level"] == 3
    assert pc["module_data"]["character_sheet"]["stats"] == {"body": 8, "mind": 5}
    assert pc["status"] == "alive"  # narrative field preserved


def test_mirror_adds_pc_entry_when_dm_emitted_none():
    # The DM followed the new prompt and wrote no PC entry — the level-up must still
    # reach the UI.
    hint = {"characters": []}
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8})
    assert len(hint["characters"]) == 1
    pc = hint["characters"][0]
    assert pc["name"] == "Kael" and pc["level"] == 3
    assert pc["module_data"]["character_sheet"]["stats"] == {"body": 8}


def test_mirror_tolerates_malformed_hint():
    _mirror_progression_to_hint(None, "Kael", 3, {})  # no raise
    _mirror_progression_to_hint({"characters": "oops"}, "Kael", 3, {})  # no raise


def test_mirror_enriches_existing_pool_with_grown_max():
    # RFC-0018: when the DM emits a pool (carrying current), the mirror adds the
    # grown hp.max / magic_pool.max so the level-up's vitality shows live.
    hint = {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "level": 2,
                "module_data": {
                    "character_sheet": {
                        "hp": {"current": 64, "max": 56},
                        "magic_pool": {"current": 16, "max": 14},
                    }
                },
            }
        ]
    }
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8}, (64, 16))
    sheet = hint["characters"][0]["module_data"]["character_sheet"]
    assert sheet["hp"] == {"current": 64, "max": 64}  # current preserved, max grown
    assert sheet["magic_pool"] == {"current": 16, "max": 16}


def test_mirror_never_emits_partial_maxonly_pool():
    # When the DM emitted no pool, the mirror must NOT create a bare {max}-only pool
    # (it would render an empty vitality bar until hydration; codex P2).
    hint = {"characters": [{"name": "Kael", "role": "player", "level": 2}]}
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8}, (64, 16))
    sheet = hint["characters"][0]["module_data"]["character_sheet"]
    assert "hp" not in sheet and "magic_pool" not in sheet


def test_mirror_skips_none_maxes_fail_safe():
    # A free-text class (no engine-owned max) → the mirror leaves an existing pool's
    # max untouched rather than writing a null.
    hint = {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "level": 2,
                "module_data": {"character_sheet": {"hp": {"current": 30, "max": 40}}},
            }
        ]
    }
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8}, (None, None))
    sheet = hint["characters"][0]["module_data"]["character_sheet"]
    assert sheet["hp"] == {"current": 30, "max": 40}  # untouched


# ── every-turn vitality normalization (RFC-0018 fast-follow) ──────────────────


def _hint(sheet):
    return {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "module_data": {"character_sheet": sheet},
            }
        ]
    }


def _sheet_of(hint):
    return hint["characters"][0]["module_data"]["character_sheet"]


WARRIOR_V = {"hp_max": 48, "magic_pool_max": None, "strip_magic_pool": True}
NONE_V = {"hp_max": None, "magic_pool_max": None, "strip_magic_pool": False}


def test_normalize_overrides_dm_inflated_max():
    # The DM writes an inflated max on an ordinary turn; enforcement rejects it in
    # the payload, so the hint must show the authoritative value — otherwise the
    # rejected number sticks in the UI until reload.
    hint = _hint({"hp": {"current": 30, "max": 999}})
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    assert _sheet_of(hint)["hp"] == {"current": 30, "max": 48}  # current untouched


def test_normalize_strips_non_caster_pool_with_deletion_marker():
    # An explicit None, not a dropped key: the client reducer treats an ABSENT key
    # as "preserve stored", so a legacy/hallucinated pool would otherwise survive
    # in the UI after enforcement removed it from the write (codex).
    hint = _hint(
        {"hp": {"current": 30, "max": 48}, "magic_pool": {"current": 5, "max": 10}}
    )
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    assert _sheet_of(hint)["magic_pool"] is None


def test_normalize_mirrors_complete_grown_pool_when_dm_emitted_none():
    # The RFC-0018 prompts tell the DM not to write vitality on a level-up, so a
    # growth turn's hint usually has no hp block at all. The complete engine pool
    # must be synthesized or the UI sits at the old value until reload (codex).
    hint = _hint({"stats": {"body": 8}})
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 64,
            "magic_pool_max": None,
            "strip_magic_pool": True,
            "hp_pool": {"current": 38, "max": 64},
            "magic_pool": None,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 38, "max": 64}


def test_normalize_growth_pool_overrides_a_dm_emitted_current():
    # Even when the DM DID emit a pool, enforcement replaces current with
    # stored+growth — the hint must show that, not the DM's current.
    hint = _hint({"hp": {"current": 99, "max": 99}})
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 64,
            "magic_pool_max": None,
            "strip_magic_pool": False,
            "hp_pool": {"current": 38, "max": 64},
            "magic_pool": None,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 38, "max": 64}


def test_normalize_sets_caster_pool_max():
    hint = _hint({"magic_pool": {"current": 12, "max": 99}})
    _normalize_vitality_hint(
        hint, "Kael", {"hp_max": 12, "magic_pool_max": 16, "strip_magic_pool": False}
    )
    assert _sheet_of(hint)["magic_pool"] == {"current": 12, "max": 16}


def test_normalize_fail_safe_leaves_dm_max():
    # Free-text class / dead PC → engine owns nothing; the DM's max stands and no
    # pool is stripped.
    hint = _hint(
        {"hp": {"current": 30, "max": 200}, "magic_pool": {"current": 4, "max": 8}}
    )
    _normalize_vitality_hint(hint, "Kael", NONE_V)
    assert _sheet_of(hint)["hp"]["max"] == 200
    assert _sheet_of(hint)["magic_pool"] == {"current": 4, "max": 8}


def test_normalize_never_invents_a_pool():
    # The DM emitted no hp block — don't create a {max}-only pool (empty bar).
    hint = _hint({"stats": {"body": 6}})
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    assert "hp" not in _sheet_of(hint)


def test_normalize_does_not_create_a_pc_entry():
    # An untouched PC needs no correction — don't synthesize an entry.
    hint = {"characters": []}
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    assert hint["characters"] == []


def test_normalize_tolerates_malformed_hints():
    _normalize_vitality_hint(None, "Kael", WARRIOR_V)  # no raise
    _normalize_vitality_hint({"characters": "oops"}, "Kael", WARRIOR_V)
    _normalize_vitality_hint(_hint("not-a-dict"), "Kael", WARRIOR_V)
    hint = _hint({"hp": "oops"})
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    assert _sheet_of(hint)["hp"] == "oops"  # untouched, no crash
