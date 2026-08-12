"""Entity-identity hardening — imposter PCs can't be minted or resolved.

The hole: `fact_extractor` passes `role` through and upserts to a NEW slug, and
fs-manager writes an absent target, so a hallucinated `<world_update>` could
introduce `0-imposter` with `role:"player"`. Characters load in filename order, so
it sorted ahead of the real PC and BECAME it — and since its name/slug differed
from the session PC, `enforce_progression` never matched it, so it could carry
`level: 5` and maxed stats. Every RFC-0017/0018/0019 invariant was bypassable.

Two halves, tested together here: minting is blocked (`enforce_pc_identity`) and
resolution is anchored to the session name (`find_player_character`).
"""

from engine import progression
from engine.death_stakes import find_player_character
from engine.identity import enforce_pc_identity

ARCHETYPES = ("warrior", "rogue", "mage", "cleric")


def _op(slug, **data):
    return {
        "target_file": f"data/state/core/entities/{slug}.json",
        "operation": "update",
        "data": data,
    }


def _payload(ops):
    return {"session_id": "s", "log_entry": "x" * 10, "updates": ops}


# ── minting: the role claim is neutralized, the character survives ────────────


def test_imposter_role_claim_is_stripped_entity_survives_as_npc():
    payload = _payload(
        [_op("0-imposter", name="0-imposter", role="player", level=5, description="hi")]
    )
    notices = enforce_pc_identity(payload, "Sal")
    data = payload["updates"][0]["data"]
    assert "role" not in data  # the CLAIM is gone…
    assert (
        data["name"] == "0-imposter" and data["description"] == "hi"
    )  # …not the entity
    assert any("player character" in n for n in notices)


def test_the_real_pc_keeps_its_role():
    payload = _payload([_op("sal", name="Sal", role="player", status="alive")])
    assert enforce_pc_identity(payload, "Sal") == []
    assert payload["updates"][0]["data"]["role"] == "player"


def test_pc_matched_by_slug_variant_keeps_its_role():
    # "O Neil" and stored "O'Neil" are both o_neil.json.
    payload = _payload([_op("o_neil", name="O Neil", role="player")])
    assert enforce_pc_identity(payload, "O'Neil") == []
    assert payload["updates"][0]["data"]["role"] == "player"


def test_npcs_keep_their_own_roles():
    payload = _payload([_op("borin", name="Borin", role="npc")])
    assert enforce_pc_identity(payload, "Sal") == []
    assert payload["updates"][0]["data"]["role"] == "npc"


def test_multiple_imposters_are_all_stripped_and_named_once():
    payload = _payload(
        [
            _op("0-imposter", name="0-imposter", role="player"),
            _op("0-imposter", name="0-imposter", role="PLAYER"),
            _op("aaa", name="Aaa", role="player"),
        ]
    )
    notices = enforce_pc_identity(payload, "Sal")
    assert all("role" not in op["data"] for op in payload["updates"])
    assert len(notices) == 1
    assert notices[0].count("0-imposter") == 1  # de-duped


def test_guard_is_inert_without_a_session_pc_name():
    # No anchor → we can't tell the PC from an imposter; don't strip everything.
    payload = _payload([_op("someone", name="Someone", role="player")])
    assert enforce_pc_identity(payload, "") == []
    assert payload["updates"][0]["data"]["role"] == "player"


def test_non_entity_ops_and_malformed_payloads_are_untouched():
    payload = _payload(
        [
            {
                "target_file": "data/state/core/locations/x.json",
                "operation": "update",
                "data": {"name": "X", "role": "player"},
            },
            {"target_file": "data/state/core/entities/y.json", "data": None},
            "not-an-op",
        ]
    )
    assert enforce_pc_identity(payload, "Sal") == []
    assert payload["updates"][0]["data"]["role"] == "player"  # locations aren't PCs
    assert enforce_pc_identity(None, "Sal") == []
    assert enforce_pc_identity({}, "Sal") == []
    assert enforce_pc_identity({"updates": "oops"}, "Sal") == []


# ── the regression this whole slice exists for ───────────────────────────────


def test_imposter_can_no_longer_grant_itself_level_and_stats():
    """The RFC-0017 bypass, end to end: an imposter sorting FIRST used to become
    the PC and carry level 5 + maxed stats, because enforce_progression matched on
    the session PC's name and never touched it."""
    stored = [
        {"name": "0-imposter", "role": "player", "level": 5},  # sorts first
        {
            "name": "Sal",
            "role": "player",
            "level": 2,
            "module_data": {"character_sheet": {"stats": {"body": 6}}},
        },
    ]
    # 1. Resolution is anchored to the session PC, not the earlier role claim.
    assert find_player_character(stored, "Sal")["level"] == 2

    # 2. And the minting attempt is neutralized before it can be stored at all.
    payload = _payload(
        [
            _op(
                "0-imposter",
                name="0-imposter",
                role="player",
                level=5,
                module_data={"character_sheet": {"stats": {"body": 10}}},
            )
        ]
    )
    enforce_pc_identity(payload, "Sal")
    assert "role" not in payload["updates"][0]["data"]

    # 3. Progression still refuses to grant the imposter anything: it isn't the PC,
    #    so its op is not a PC op and its level/stats are left as the DM's problem —
    #    but with no role claim it can never be resolved AS the PC next turn.
    progression.enforce_progression(
        payload,
        stored_characters=stored,
        player_name="Sal",
        choice=None,
        archetypes=ARCHETYPES,
    )
    assert "role" not in payload["updates"][0]["data"]
