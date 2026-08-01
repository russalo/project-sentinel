"""RFC-0017 — the SSE-hint mirror shows a committed level-up live (codex review).

The DM no longer writes `level`/`stats`, so without mirroring the engine-committed
values into the `world_update` hint the player wouldn't see the advance until a full
hydration.
"""

from backend.routes.stream import _mirror_progression_to_hint


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
