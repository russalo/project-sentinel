"""The SSE hint PC locators match by slug/casefold identity, not exact string
(codex + coderabbit on PR #200, convergent): enforcement and the identity
guard already used the slug predicate, so a punctuation-variant fragment was
corrected on disk but kept its rejected values in the hint."""

from backend.routes.stream import _locate_all_pc_in_hint, _locate_pc_in_hint


def test_all_locator_matches_punctuation_variant():
    hint = {
        "characters": [
            {"name": "O Neil", "level": 99},  # stored spelling differs
            {"name": "Goblin", "role": "npc"},
        ]
    }
    found = _locate_all_pc_in_hint(hint, "O'Neil")
    assert [c["name"] for c in found] == ["O Neil"]


def test_all_locator_casefold_fallback_for_unsluggable_names():
    hint = {"characters": [{"name": "李"}]}
    assert _locate_all_pc_in_hint(hint, "李") != []


def test_single_locator_matches_variant_without_creating_duplicate():
    hint = {"characters": [{"name": "O Neil"}]}
    pc = _locate_pc_in_hint(hint, "O'Neil", create=True)
    assert pc is hint["characters"][0]
    assert len(hint["characters"]) == 1  # matched, not duplicated


def test_locators_tolerate_malformed_shapes():
    assert _locate_all_pc_in_hint(None, "Kael") == []
    assert _locate_all_pc_in_hint({"characters": "x"}, "Kael") == []
    assert _locate_pc_in_hint({"characters": [None]}, "Kael", create=False) is None
