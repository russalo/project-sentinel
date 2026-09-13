"""Deterministic PC establishment at session creation (``engine/provisioning``).

The provisioned payload is the anchor every ADR-0004 mechanism attaches to
(RFC-0014/0017/0018/0019, #192 identity anchoring) — so it must be schema-valid
by construction, deterministic, archetype-honest (never guess), and honest
about unsluggable names (None, so the caller fails loud).
"""

import engine
from engine import provisioning
from engine.modules.registry import registry

SESSION_ID = "11111111-1111-1111-1111-111111111111"


def setup_function():
    registry.clear()


def teardown_function():
    registry.clear()


def _payload(name="Kael", cls="Warrior"):
    return provisioning.pc_provision_payload(SESSION_ID, name, cls)


# ── pc_provision_payload ─────────────────────────────────────────────


def test_payload_is_schema_valid_and_deterministic():
    p1, a1 = _payload()
    p2, a2 = _payload()
    assert p1 == p2
    assert a1 == a2 == "warrior"
    validation = engine.validate(p1)
    assert validation.ok, validation.errors


def test_skeleton_shape():
    payload, archetype = _payload("Kael", "Warrior")
    assert archetype == "warrior"
    (op,) = payload["updates"]
    assert op["operation"] == "create"  # fs-manager's 409 is the idempotency gate
    assert op["target_file"] == "data/state/core/entities/kael.json"
    assert op["data"] == {
        "name": "Kael",
        "class": "Warrior",
        "role": "player",
        "level": provisioning.STARTING_LEVEL,
        "archetype": "warrior",
    }
    assert payload["session_id"] == SESSION_ID
    assert payload["metadata"] == {"agent": "orchestrator", "turn_number": 0}


def test_free_text_class_gets_no_archetype():
    """RFC-0019: deriving is opt-in on a known class, never a guess — a class
    that isn't one of the module's archetypes is left for the DM mapping."""
    payload, archetype = _payload("Kael", "Swashbuckler")
    assert archetype is None
    data = payload["updates"][0]["data"]
    assert "archetype" not in data
    assert data["class"] == "Swashbuckler"  # flavor text kept verbatim


def test_archetype_match_is_case_insensitive():
    _, archetype = _payload("Kael", "  CLERIC ")
    assert archetype == "cleric"


def test_unsluggable_name_returns_no_payload():
    """Non-ASCII / empty names have no entity file the Fact-Extractor could
    target either — return None so the caller fails LOUD (pending product
    call; deliberately not solved here)."""
    for name in ["李明", "Ø∆", "", "   ", None]:
        payload, archetype = provisioning.pc_provision_payload(
            SESSION_ID, name, "Warrior"
        )
        assert payload is None, name
        assert archetype is None, name


def test_no_protected_fields_in_skeleton():
    """fs-manager's check_protected_fields runs unconditionally — even for
    namespace=core — so the skeleton must never carry one."""
    payload, _ = _payload()
    data = payload["updates"][0]["data"]
    protected = {
        "unique_id",
        "world_seed",
        "namespace",
        "created_at",
        "canon",
        "core_faction_id",
    }
    assert not protected & {k.lower() for k in data}


def test_log_entry_is_scrubbed_and_clamped():
    """The name is user text: the schema rejects control bytes, and the request
    model puts no max length on the name."""
    payload, _ = provisioning.pc_provision_payload(
        SESSION_ID, "Ka\x07el" + "x" * 5000, "Warrior"
    )
    assert payload is not None
    log_entry = payload["log_entry"]
    assert "\x07" not in log_entry
    assert len(log_entry) <= 4000
    validation = engine.validate(payload)
    assert validation.ok, validation.errors


# ── strip_payload_pc_level ───────────────────────────────────────────


def _op(target, data):
    return {"target_file": target, "operation": "update", "data": data}


def test_strip_payload_pc_level_strips_only_the_pc():
    payload = {
        "updates": [
            _op("data/state/core/entities/kael.json", {"name": "Kael", "level": 7}),
            _op("data/state/core/entities/goblin.json", {"name": "Goblin", "level": 3}),
            _op("data/state/core/world/state.json", {"level": 9}),
        ]
    }
    assert provisioning.strip_payload_pc_level(payload, "Kael") == 1
    assert "level" not in payload["updates"][0]["data"]
    assert payload["updates"][1]["data"]["level"] == 3  # NPC untouched
    assert payload["updates"][2]["data"]["level"] == 9  # non-entity untouched


def test_strip_payload_pc_level_matches_by_carried_name_too():
    """Same dual identity match as seed_payload_vitality: an op whose data
    names the PC is the PC's, whatever file it targets."""
    payload = {
        "updates": [
            _op("data/state/core/entities/hero.json", {"name": "Kael", "level": 7}),
        ]
    }
    assert provisioning.strip_payload_pc_level(payload, "Kael") == 1
    assert "level" not in payload["updates"][0]["data"]


def test_strip_payload_pc_level_tolerates_malformed_shapes():
    assert provisioning.strip_payload_pc_level(None, "Kael") == 0
    assert provisioning.strip_payload_pc_level({"updates": "nope"}, "Kael") == 0
    assert (
        provisioning.strip_payload_pc_level(
            {"updates": [None, {"target_file": 3}, _op("x", "s")]}, "Kael"
        )
        == 0
    )
    # Unsluggable anchor → no identity to match on → no-op.
    payload = {"updates": [_op("data/state/core/entities/k.json", {"level": 2})]}
    assert provisioning.strip_payload_pc_level(payload, "李") == 0


# ── pin_hint_pc_level ────────────────────────────────────────────────


def test_pin_hint_pc_level_pins_and_adds():
    hint = {
        "characters": [
            {"name": "Kael", "level": 7},
            {"name": "Goblin", "level": 3},
        ]
    }
    assert provisioning.pin_hint_pc_level(hint, "Kael", 1) == 1
    assert hint["characters"][0]["level"] == 1
    assert hint["characters"][1]["level"] == 3

    # An entry with no level at all gets the committed value mirrored in.
    hint = {"characters": [{"name": "Kael"}]}
    assert provisioning.pin_hint_pc_level(hint, "Kael", 1) == 1
    assert hint["characters"][0]["level"] == 1

    # Already correct → untouched (count 0).
    assert provisioning.pin_hint_pc_level(hint, "Kael", 1) == 0


def test_pin_hint_pc_level_none_strips_the_claim():
    """The 409 already-established case: the stored level isn't known here, so
    the DM's claim is stripped without asserting one."""
    hint = {"characters": [{"name": "Kael", "level": 7}]}
    assert provisioning.pin_hint_pc_level(hint, "Kael", None) == 1
    assert "level" not in hint["characters"][0]


def test_pin_hint_pc_level_tolerates_malformed_shapes():
    assert provisioning.pin_hint_pc_level(None, "Kael", 1) == 0
    assert provisioning.pin_hint_pc_level({"characters": {}}, "Kael", 1) == 0
    assert provisioning.pin_hint_pc_level({"characters": [None, "x"]}, "Kael", 1) == 0


# ── ensure_hint_pc ───────────────────────────────────────────────────


def test_ensure_hint_pc_appends_a_copy_when_absent():
    pc = {"name": "Kael", "class": "Warrior", "role": "player", "level": 1}
    hint = {}
    assert provisioning.ensure_hint_pc(hint, pc) is True
    assert hint["characters"] == [pc]
    assert hint["characters"][0] is not pc  # a copy — hint mutation can't leak back


def test_ensure_hint_pc_defers_to_an_existing_entry():
    pc = {"name": "O'Neil", "role": "player", "level": 1}
    # Slug-equivalent spelling counts as present (same entity file).
    hint = {"characters": [{"name": "O Neil", "role": "npc"}]}
    assert provisioning.ensure_hint_pc(hint, pc) is False
    assert len(hint["characters"]) == 1


def test_ensure_hint_pc_tolerates_malformed_shapes():
    pc = {"name": "Kael"}
    assert provisioning.ensure_hint_pc(None, pc) is False
    assert provisioning.ensure_hint_pc({"characters": "oops"}, pc) is False
    assert provisioning.ensure_hint_pc({}, None) is False
    assert provisioning.ensure_hint_pc({}, {"name": "李"}) is False  # no slug
    hint = {"characters": [None, "x"]}
    assert provisioning.ensure_hint_pc(hint, pc) is True  # junk entries skipped
    assert hint["characters"][-1] == {"name": "Kael"}
