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


def test_mirror_carries_derived_maxes():
    # RFC-0018: a level-up that grows Body/Will must surface the new hp.max /
    # magic_pool.max live, not only after hydration.
    hint = {"characters": [{"name": "Kael", "role": "player", "level": 2}]}
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8}, (64, 16))
    sheet = hint["characters"][0]["module_data"]["character_sheet"]
    assert sheet["hp"]["max"] == 64
    assert sheet["magic_pool"]["max"] == 16


def test_mirror_skips_none_maxes_fail_safe():
    # A free-text class (no engine-owned max) → the mirror leaves hp/magic_pool
    # untouched rather than writing a null max.
    hint = {"characters": [{"name": "Kael", "role": "player", "level": 2}]}
    _mirror_progression_to_hint(hint, "Kael", 3, {"body": 8}, (None, None))
    sheet = hint["characters"][0]["module_data"]["character_sheet"]
    assert "hp" not in sheet and "magic_pool" not in sheet
