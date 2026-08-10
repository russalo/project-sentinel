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
            "hp_growth": 8,
            "magic_growth": 0,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 38, "max": 64}


def test_normalize_growth_pool_overrides_a_dm_emitted_current():
    # Even when the DM DID emit a pool, enforcement replaces current with
    # stored+growth on a GROWTH turn — the hint must show that, not the DM's.
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
            "hp_growth": 8,
            "magic_growth": 0,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 38, "max": 64}


def test_normalize_non_growth_keeps_dm_current_corrects_max():
    # No growth: the DM's narrative current (damage this turn) survives; only the
    # engine-owned max is corrected.
    hint = _hint({"hp": {"current": 12, "max": 999}})
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 48,
            "magic_pool_max": None,
            "strip_magic_pool": False,
            "hp_pool": {"current": 30, "max": 48},
            "magic_pool": None,
            "hp_growth": 0,
            "magic_growth": 0,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 12, "max": 48}


def test_normalize_creates_sheet_for_a_status_only_pc_hint():
    # A status/combat-only PC hint still has its vitality corrected — enforcement
    # is fixing the persisted state, and the client's deep merge would otherwise
    # keep the stale max / stripped pool until reload (codex).
    hint = {
        "characters": [
            {"name": "Kael", "role": "player", "status": "unconscious"},
        ]
    }
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 48,
            "magic_pool_max": None,
            "strip_magic_pool": True,
            "hp_pool": {"current": 0, "max": 48},
            "magic_pool": None,
            "hp_growth": 0,
            "magic_growth": 0,
        },
    )
    sheet = _sheet_of(hint)
    assert sheet["hp"] == {"current": 0, "max": 48}
    assert sheet["magic_pool"] is None  # deletion marker reaches the client


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
    # No crash; the malformed pool is replaced with the same seed enforcement
    # commits (see test_normalize_malformed_pool_matches_enforcement_seed).
    assert _sheet_of(hint)["hp"] == {"current": 48, "max": 48}


def test_normalize_patches_every_pc_fragment():
    # The DM emitted the PC twice; the client applies fragments in order, so an
    # unnormalized later one would restore the rejected max (codex).
    hint = {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "module_data": {"character_sheet": {"hp": {"current": 30, "max": 999}}},
            },
            {
                "name": "Kael",
                "action": "upsert",
                "module_data": {"character_sheet": {"hp": {"current": 25, "max": 777}}},
            },
        ]
    }
    _normalize_vitality_hint(hint, "Kael", WARRIOR_V)
    sheets = [c["module_data"]["character_sheet"] for c in hint["characters"]]
    assert [s["hp"]["max"] for s in sheets] == [48, 48]  # both corrected
    assert [s["hp"]["current"] for s in sheets] == [30, 25]  # currents preserved
    assert all(s["magic_pool"] is None for s in sheets)  # marker on both


def test_normalize_malformed_pool_matches_enforcement_seed():
    # A non-object hp from the LLM: enforcement's _as_dict drops it and _apply_max
    # seeds current = max (48/48). The hint must show the same, not the stored
    # current — else the bar reads wounded while persistence has full health.
    hint = _hint({"hp": "oops"})
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 48,
            "magic_pool_max": None,
            "strip_magic_pool": False,
            "hp_pool": {"current": 30, "max": 48},  # stored current — NOT used here
            "magic_pool": None,
            "hp_growth": 0,
            "magic_growth": 0,
        },
    )
    assert _sheet_of(hint)["hp"] == {"current": 48, "max": 48}


def test_normalize_malformed_pool_left_alone_when_engine_owns_nothing():
    hint = _hint({"hp": "oops"})
    _normalize_vitality_hint(hint, "Kael", NONE_V)
    assert _sheet_of(hint)["hp"] == "oops"  # fail-safe, untouched


def test_normalize_later_fragment_does_not_undo_earlier_damage():
    # damage fragment then a status-only fragment: the later one must NOT be
    # synthesized from the pre-turn pool, or the client would apply 20 then snap
    # back to the stored 30 while persistence (which carries ops forward via
    # base_md) stayed at 20 (codex).
    hint = {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "module_data": {"character_sheet": {"hp": {"current": 20, "max": 48}}},
            },
            {"name": "Kael", "action": "upsert", "status": "unconscious"},
        ]
    }
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 48,
            "magic_pool_max": None,
            "strip_magic_pool": False,
            "hp_pool": {"current": 30, "max": 48},  # pre-turn stored
            "magic_pool": None,
            "hp_growth": 0,
            "magic_growth": 0,
        },
    )
    first, second = (c["module_data"]["character_sheet"] for c in hint["characters"])
    assert first["hp"] == {"current": 20, "max": 48}  # damage kept
    assert "hp" not in second  # not re-synthesized → client keeps 20


def test_normalize_growth_pool_reaches_every_fragment():
    # On a GROWTH turn `may_synthesize` deliberately does not gate the override:
    # enforcement's _apply_max sets current = stored+growth on EVERY matching op,
    # so a later fragment that omits the pool must still carry the grown one or
    # the client would keep the pre-growth value (coderabbit).
    hint = {
        "characters": [
            {
                "name": "Kael",
                "role": "player",
                "module_data": {"character_sheet": {"hp": {"current": 30, "max": 56}}},
            },
            {"name": "Kael", "action": "upsert", "status": "alive"},
        ]
    }
    _normalize_vitality_hint(
        hint,
        "Kael",
        {
            "hp_max": 64,
            "magic_pool_max": None,
            "strip_magic_pool": False,
            "hp_pool": {"current": 38, "max": 64},
            "magic_pool": None,
            "hp_growth": 8,
            "magic_growth": 0,
        },
    )
    sheets = [c["module_data"]["character_sheet"] for c in hint["characters"]]
    assert all(s["hp"] == {"current": 38, "max": 64} for s in sheets)


# ── RFC-0019: picking the DM's establishing archetype ────────────────────────

from backend.routes.stream import _incoming_archetype_candidate  # noqa: E402

VALID = ("warrior", "rogue", "mage", "cleric")


def _blocks(*payloads):
    import json as _j

    return " narrative ".join(
        f"<world_update>{_j.dumps(p)}</world_update>" for p in payloads
    )


def test_candidate_skips_invalid_and_scans_all_blocks():
    # codex: taking the first TRUTHY value from only the FIRST block let a leading
    # junk slug shadow a valid one — the pin came back None and enforcement then
    # dropped the good write too. The Fact-Extractor reads every block, so we must.
    raw = _blocks(
        {"characters": [{"name": "Bran", "archetype": "paladin"}]},
        {"characters": [{"name": "Bran", "archetype": "Cleric"}]},
    )
    assert _incoming_archetype_candidate(raw, "Bran", VALID) == "cleric"


def test_candidate_ignores_entries_the_extractor_would_discard():
    # codex: a role-only fragment (or one named for someone else) never reaches the
    # PC's entity file — the Fact-Extractor builds the target from the NAME — so its
    # archetype must not become the pin and get forced onto the PC forever.
    raw = _blocks({"characters": [{"role": "player", "archetype": "warrior"}]})
    assert _incoming_archetype_candidate(raw, "Bran", VALID) is None
    raw2 = _blocks(
        {"characters": [{"name": "Someone", "role": "player", "archetype": "mage"}]}
    )
    assert _incoming_archetype_candidate(raw2, "Bran", VALID) is None
    # …and a properly named PC entry still counts.
    raw3 = _blocks(
        {
            "characters": [
                {"role": "player", "archetype": "warrior"},
                {"name": "Bran", "archetype": "cleric"},
            ]
        }
    )
    assert _incoming_archetype_candidate(raw3, "Bran", VALID) == "cleric"


def test_candidate_ignores_non_pc_entries():
    raw = _blocks(
        {"characters": [{"name": "Borin", "role": "npc", "archetype": "warrior"}]}
    )
    assert _incoming_archetype_candidate(raw, "Bran", VALID) is None


def test_candidate_tolerates_malformed_and_empty():
    assert (
        _incoming_archetype_candidate(
            "<world_update>{oops</world_update>", "Bran", VALID
        )
        is None
    )
    assert _incoming_archetype_candidate("no blocks here", "Bran", VALID) is None
    assert _incoming_archetype_candidate(None, "Bran", VALID) is None
    assert (
        _incoming_archetype_candidate(_blocks({"characters": "oops"}), "Bran", VALID)
        is None
    )
    # Inert when the world has no archetypes at all.
    assert (
        _incoming_archetype_candidate(
            _blocks({"characters": [{"name": "Bran", "archetype": "mage"}]}), "Bran", ()
        )
        is None
    )


def test_normalize_archetype_hint_forces_the_pin():
    from backend.routes.stream import _normalize_archetype_hint

    hint = {"characters": [{"name": "Bran", "role": "player", "archetype": "warrior"}]}
    _normalize_archetype_hint(hint, "Bran", "cleric")
    assert hint["characters"][0]["archetype"] == "cleric"


def test_normalize_archetype_hint_removes_when_unpinned():
    from backend.routes.stream import _normalize_archetype_hint

    hint = {"characters": [{"name": "Bran", "role": "player", "archetype": "paladin"}]}
    _normalize_archetype_hint(hint, "Bran", None)
    assert "archetype" not in hint["characters"][0]


def test_normalize_archetype_hint_touches_every_fragment():
    from backend.routes.stream import _normalize_archetype_hint

    hint = {
        "characters": [
            {"name": "Bran", "role": "player", "archetype": "warrior"},
            {"name": "Bran", "archetype": "mage"},
        ]
    }
    _normalize_archetype_hint(hint, "Bran", "cleric")
    assert [c["archetype"] for c in hint["characters"]] == ["cleric", "cleric"]


def test_candidate_matches_the_extracted_slug_not_the_exact_name():
    # codex: stored "O'Neil" vs emitted "O Neil" both target o_neil.json, so
    # enforcement treats it as the PC write — an exact-string check would drop the
    # valid archetype and leave a free-text PC unresolved.
    raw = _blocks({"characters": [{"name": "O Neil", "archetype": "cleric"}]})
    assert _incoming_archetype_candidate(raw, "O'Neil", VALID) == "cleric"
