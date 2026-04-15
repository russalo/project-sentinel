"""Unit tests for engine.agents.fact_extractor.extract.

Tests are pure — no Django, no network, no filesystem reads beyond the
schema file the extractor loads via engine.validate(). Every case
round-trips through the real engine.validate() so a passing test proves
the output is actually fs-manager-compatible.
"""

import json

import pytest

from engine.agents.fact_extractor import (
    FactExtractResult,
    extract,
)
from engine.schema import validate

VALID_SESSION_ID = "123e4567-e89b-12d3-a456-426614174000"


def _wrap(narrative: str, block: dict | str) -> str:
    block_str = json.dumps(block) if isinstance(block, dict) else block
    return f"{narrative}\n<world_update>\n{block_str}\n</world_update>\n"


# ── no block / malformed input ──────────────────────────────────────


def test_no_block_returns_none_payload_but_preserves_narrative():
    raw = "The tavern is quiet. Nothing has changed."
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert isinstance(result, FactExtractResult)
    assert result.payload is None
    assert "tavern" in result.narrative
    assert result.errors == []


def test_malformed_json_block_returns_none_with_error():
    raw = "<world_update>{this is not json}</world_update>"
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is None
    assert any("not valid JSON" in e for e in result.errors)


def test_non_object_block_returns_none_with_error():
    raw = "<world_update>[1, 2, 3]</world_update>"
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is None
    assert any("expected object" in e for e in result.errors)


def test_empty_block_returns_none_payload():
    raw = _wrap("Stillness.", {})
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is None


# ── entity round-trips ──────────────────────────────────────────────


def test_character_upsert_produces_valid_payload():
    raw = _wrap(
        "You meet Kael by the fire, his eyes sharp and cautious.",
        {
            "characters": [
                {
                    "name": "Kael",
                    "action": "upsert",
                    "role": "npc",
                    "health": 80,
                    "status": "alive",
                    "currentLocation": "Crossroads Tavern",
                    "description": "A weary traveler",
                    "traits": ["cautious", "observant"],
                }
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=3)
    assert result.payload is not None

    assert result.payload["session_id"] == VALID_SESSION_ID
    assert len(result.payload["updates"]) == 1

    update = result.payload["updates"][0]
    assert update["target_file"] == "data/state/core/entities/kael.json"
    assert update["operation"] == "update"
    # `action` field should be stripped from the stored data
    assert "action" not in update["data"]
    assert update["data"]["role"] == "npc"
    assert update["data"]["traits"] == ["cautious", "observant"]

    assert validate(result.payload).ok


def test_location_upsert_produces_valid_payload():
    raw = _wrap(
        "The Crossroads Tavern emerges from the fog, warm light through shutters.",
        {
            "locations": [
                {
                    "name": "Crossroads Tavern",
                    "action": "upsert",
                    "type": "tavern",
                    "description": "A warm refuge at the meeting of three roads",
                    "discovered": True,
                    "danger": 1,
                }
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    assert (
        result.payload["updates"][0]["target_file"]
        == "data/state/core/locations/crossroads_tavern.json"
    )
    assert validate(result.payload).ok


def test_faction_upsert_produces_valid_payload():
    raw = _wrap(
        "You overhear talk of the Grey Pact — old and dangerous.",
        {
            "factions": [
                {
                    "name": "The Grey Pact",
                    "action": "upsert",
                    "alignment": "neutral",
                    "power": 7,
                    "playerRelation": -2,
                }
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=2)
    assert result.payload is not None
    assert (
        result.payload["updates"][0]["target_file"]
        == "data/state/core/factions/the_grey_pact.json"
    )
    assert validate(result.payload).ok


def test_item_upsert_produces_valid_payload():
    raw = _wrap(
        "A heavy iron key clatters onto the bar.",
        {
            "items": [
                {
                    "name": "Iron Key",
                    "action": "upsert",
                    "type": "key",
                    "rarity": "common",
                    "ownedBy": "Kael",
                }
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    assert (
        result.payload["updates"][0]["target_file"]
        == "data/state/core/items/iron_key.json"
    )
    assert validate(result.payload).ok


def test_world_block_produces_single_world_file_update():
    raw = _wrap(
        "A chill wind rises from the north; the sky darkens.",
        {
            "world": {
                "currentLocation": "Crossroads Tavern",
                "weather": "Cold wind, gathering clouds",
                "timeOfDay": "Dusk",
                "tension": 4,
            }
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=5)
    assert result.payload is not None
    update = result.payload["updates"][0]
    assert update["target_file"] == "data/state/core/world/state.json"
    assert update["operation"] == "update"
    assert update["data"]["tension"] == 4
    assert validate(result.payload).ok


def test_multiple_collections_combined_into_single_payload():
    raw = _wrap(
        "You enter the tavern. Kael nods from the corner; a torch flickers on the wall.",
        {
            "world": {"currentLocation": "Crossroads Tavern", "tension": 3},
            "characters": [
                {"name": "Kael", "action": "upsert", "role": "npc", "status": "alive"}
            ],
            "items": [{"name": "Wall Torch", "action": "upsert", "type": "misc"}],
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=2)
    assert result.payload is not None
    targets = {u["target_file"] for u in result.payload["updates"]}
    assert "data/state/core/world/state.json" in targets
    assert "data/state/core/entities/kael.json" in targets
    assert "data/state/core/items/wall_torch.json" in targets
    assert validate(result.payload).ok


# ── slugification ───────────────────────────────────────────────────


def test_slugifies_names_with_punctuation_and_spaces():
    raw = _wrap(
        "You find the Old Dragon's Lair carved into the cliff face.",
        {
            "locations": [
                {
                    "name": "Old Dragon's Lair",
                    "action": "upsert",
                    "type": "cave",
                    "description": "Ancient and cold",
                }
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    target = result.payload["updates"][0]["target_file"]
    # apostrophe, spaces → underscores; collapsed; lowercase
    assert target == "data/state/core/locations/old_dragon_s_lair.json"
    assert validate(result.payload).ok


def test_unusable_name_is_skipped_with_error():
    raw = _wrap(
        "Something stirs in the dark.",
        {
            "characters": [
                {"name": "!!!", "action": "upsert", "role": "enemy"},
                {"name": "Shadow Wolf", "action": "upsert", "role": "enemy"},
            ]
        },
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    # Only the slugifiable entry survives
    assert len(result.payload["updates"]) == 1
    assert (
        result.payload["updates"][0]["target_file"]
        == "data/state/core/entities/shadow_wolf.json"
    )
    assert any("missing usable name" in e for e in result.errors)


def test_missing_name_field_is_skipped_with_error():
    raw = _wrap(
        "A shadow moves.",
        {"characters": [{"action": "upsert", "role": "enemy"}]},
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is None  # nothing usable
    assert any("missing usable name" in e for e in result.errors)


# ── log_entry bounds ────────────────────────────────────────────────


def test_short_narrative_is_padded_to_meet_minlength():
    raw = _wrap("Huh.", {"world": {"tension": 5}})
    result = extract(raw, VALID_SESSION_ID, turn_number=7)
    assert result.payload is not None
    log_entry = result.payload["log_entry"]
    assert len(log_entry) >= 10
    assert "turn 7" in log_entry
    assert validate(result.payload).ok


def test_empty_narrative_is_padded_to_meet_minlength():
    raw = _wrap("", {"world": {"tension": 2}})
    result = extract(raw, VALID_SESSION_ID, turn_number=0)
    assert result.payload is not None
    assert len(result.payload["log_entry"]) >= 10


def test_long_narrative_is_truncated_with_ellipsis():
    long_text = "The fog rolls in. " * 500  # ~9500 chars
    raw = _wrap(long_text, {"world": {"tension": 6}})
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    log_entry = result.payload["log_entry"]
    assert len(log_entry) <= 4000
    assert log_entry.endswith("...")
    assert validate(result.payload).ok


# ── metadata / confidence ───────────────────────────────────────────


def test_metadata_includes_turn_and_agent():
    raw = _wrap("Things happen.", {"world": {"tension": 3}})
    result = extract(raw, VALID_SESSION_ID, turn_number=42)
    assert result.payload is not None
    metadata = result.payload["metadata"]
    assert metadata["agent"] == "fact-extractor"
    assert metadata["turn_number"] == 42
    assert "confidence" not in metadata  # omitted when not provided


def test_metadata_includes_confidence_when_provided():
    raw = _wrap("Things happen.", {"world": {"tension": 3}})
    result = extract(raw, VALID_SESSION_ID, turn_number=1, confidence=0.87)
    assert result.payload is not None
    assert result.payload["metadata"]["confidence"] == 0.87


# ── unknown keys / malformed subsections ────────────────────────────


def test_unknown_top_level_key_yields_warning_but_does_not_crash():
    raw = _wrap(
        "A vague sense of change.",
        {"world": {"tension": 5}, "wizards": [{"name": "Gandalf"}]},
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None  # world still processed
    assert any("wizards" in e for e in result.errors)


def test_non_list_collection_yields_error_but_other_collections_still_work():
    raw = _wrap(
        "The wind changes.",
        {"world": {"tension": 4}, "characters": "not a list"},
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    assert len(result.payload["updates"]) == 1  # only the world update
    assert any("expected list" in e for e in result.errors)


# ── invalid session_id surfaces as self-validation error ────────────


def test_multiple_world_update_blocks_are_all_processed():
    """If the LLM emits more than one <world_update> block, every block
    must be processed. The narrative stripper removes all of them, so
    losing any block here would be silent data loss.
    """
    raw = (
        "You meet Kael by the fire.\n"
        "<world_update>\n"
        '{"characters": [{"name": "Kael", "action": "upsert", "role": "npc", "status": "alive"}]}\n'
        "</world_update>\n"
        "The fire crackles; a second figure emerges from the shadows.\n"
        "<world_update>\n"
        '{"characters": [{"name": "Mira", "action": "upsert", "role": "ally", "status": "alive"}]}\n'
        "</world_update>\n"
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)

    assert result.payload is not None
    targets = {u["target_file"] for u in result.payload["updates"]}
    assert "data/state/core/entities/kael.json" in targets
    assert "data/state/core/entities/mira.json" in targets
    # The narrative stripper removed both blocks; make sure the
    # Fact-Extractor still saw both.
    assert "<world_update>" not in result.narrative
    # And the extractor warned about the unexpected multi-block case
    assert any("found 2 <world_update> blocks" in e for e in result.errors)


def test_multiple_blocks_merge_updates_in_order():
    """Multi-block output produces updates[] in block-then-entry order,
    so a later block's update to an already-mentioned entity naturally
    wins at the fs-manager merge step."""
    raw = (
        "Kael looks hurt.\n"
        "<world_update>\n"
        '{"characters": [{"name": "Kael", "action": "upsert", "health": 80}]}\n'
        "</world_update>\n"
        "But then he takes a bigger wound.\n"
        "<world_update>\n"
        '{"characters": [{"name": "Kael", "action": "upsert", "health": 50}]}\n'
        "</world_update>\n"
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    updates = result.payload["updates"]
    # Two updates against the same target file, in order
    assert len(updates) == 2
    assert updates[0]["target_file"] == "data/state/core/entities/kael.json"
    assert updates[1]["target_file"] == "data/state/core/entities/kael.json"
    assert updates[0]["data"]["health"] == 80
    assert updates[1]["data"]["health"] == 50


def test_one_of_multiple_blocks_malformed_others_still_processed():
    """A malformed block should surface an error but not poison the
    other blocks — the good ones still produce updates."""
    raw = (
        "<world_update>\n"
        '{"world": {"tension": 5}}\n'
        "</world_update>\n"
        "<world_update>\n"
        "{this is not json}\n"
        "</world_update>\n"
        "<world_update>\n"
        '{"characters": [{"name": "Kael", "action": "upsert", "role": "npc", "status": "alive"}]}\n'
        "</world_update>\n"
    )
    result = extract(raw, VALID_SESSION_ID, turn_number=1)
    assert result.payload is not None
    targets = [u["target_file"] for u in result.payload["updates"]]
    assert "data/state/core/world/state.json" in targets
    assert "data/state/core/entities/kael.json" in targets
    assert any("block 1 is not valid JSON" in e for e in result.errors)
    assert any("found 3 <world_update> blocks" in e for e in result.errors)


def test_invalid_uuid_session_id_self_validation_fails():
    raw = _wrap("A moment passes.", {"world": {"tension": 2}})
    result = extract(raw, "not-a-uuid", turn_number=1)
    assert result.payload is None
    assert any("self-validation failed" in e for e in result.errors)
    assert any("uuid" in e.lower() for e in result.errors)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
