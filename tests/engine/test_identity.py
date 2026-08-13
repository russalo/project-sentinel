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
    assert data["role"] == "npc"  # demoted, not merely omitted…
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
    assert all(op["data"]["role"] == "npc" for op in payload["updates"])
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
    assert payload["updates"][0]["data"]["role"] == "npc"

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
    assert payload["updates"][0]["data"]["role"] == "npc"


# ── the HINT is the other half: the client acts on it before the payload lands ─


def test_hint_imposter_claim_is_stripped():
    from engine.identity import sanitize_hint_pc_identity

    hint = {
        "characters": [
            {"name": "0-imposter", "role": "player", "level": 5},
            {"name": "Sal", "role": "player"},
            {"name": "Borin", "role": "npc"},
        ]
    }
    notices = sanitize_hint_pc_identity(hint, "Sal")
    assert hint["characters"][0]["role"] == "npc"  # demoted, not omitted
    assert hint["characters"][0]["level"] == 5  # character otherwise intact
    assert hint["characters"][1]["role"] == "player"  # the real PC keeps it
    assert hint["characters"][2]["role"] == "npc"
    assert any("player character" in n for n in notices)


def test_hint_sanitizer_matches_the_pc_by_slug_and_is_inert_without_a_name():
    from engine.identity import sanitize_hint_pc_identity

    hint = {"characters": [{"name": "O Neil", "role": "player"}]}
    assert sanitize_hint_pc_identity(hint, "O'Neil") == []
    assert hint["characters"][0]["role"] == "player"

    hint2 = {"characters": [{"name": "Someone", "role": "player"}]}
    assert sanitize_hint_pc_identity(hint2, "") == []
    assert hint2["characters"][0]["role"] == "player"


def test_hint_sanitizer_tolerates_malformed_input():
    from engine.identity import sanitize_hint_pc_identity

    assert sanitize_hint_pc_identity(None, "Sal") == []
    assert sanitize_hint_pc_identity({}, "Sal") == []
    assert sanitize_hint_pc_identity({"characters": "oops"}, "Sal") == []
    assert sanitize_hint_pc_identity({"characters": [None, 7]}, "Sal") == []


def test_hint_sanitization_must_precede_pc_location():
    """The ordering constraint: `_locate_pc_in_hint` prefers role=="player", so an
    unsanitized imposter would be mistaken for the PC by the vitality/archetype
    normalizers and have the real PC's authoritative fields copied onto it."""
    from backend.routes.stream import _locate_pc_in_hint
    from engine.identity import sanitize_hint_pc_identity

    def build():
        return {
            "characters": [
                {"name": "0-imposter", "role": "player"},
                {"name": "Sal", "role": "player"},
            ]
        }

    # Before sanitization the imposter IS what the normalizers would target…
    assert _locate_pc_in_hint(build(), "Sal", create=False)["name"] == "0-imposter"
    # …and after, they correctly target the real PC.
    hint = build()
    sanitize_hint_pc_identity(hint, "Sal")
    assert _locate_pc_in_hint(hint, "Sal", create=False)["name"] == "Sal"


# ── round-2 review fixes ─────────────────────────────────────────────────────


def test_claim_is_authorized_by_target_path_not_by_name():
    """coderabbit: an op for entities/imposter.json carrying {"name": "Sal"} used to
    pass a name-based check and write a player role onto the IMPOSTER entity."""
    payload = _payload([_op("imposter", name="Sal", role="player")])
    notices = enforce_pc_identity(payload, "Sal")
    assert payload["updates"][0]["data"]["role"] == "npc"
    assert notices
    # …while the PC's own file is still authorized.
    ok = _payload([_op("sal", name="Sal", role="player")])
    assert enforce_pc_identity(ok, "Sal") == []
    assert ok["updates"][0]["data"]["role"] == "player"


def test_demotion_overwrites_a_previously_stored_claim():
    """codex: fs-manager applies `existing.update(data)`, so omitting `role` would
    leave a stored role:"player" in place — the write must demote explicitly."""
    payload = _payload([_op("0-imposter", name="0-imposter", role="player")])
    enforce_pc_identity(payload, "Sal")
    # The dispatched op carries an explicit demotion that the shallow merge applies.
    assert payload["updates"][0]["data"]["role"] == "npc"


def test_an_unsluggable_player_name_still_anchors():
    """codex: `_slugify` returns None for a name with no ASCII slug characters, and
    NewSessionRequest imposes no charset — treating that as "no identity" disabled
    the guard AND made the resolver trust the first role:"player" entity."""
    payload = _payload([_op("0-imposter", name="0-imposter", role="player")])
    assert enforce_pc_identity(payload, "李")  # guard is NOT disabled
    assert payload["updates"][0]["data"]["role"] == "npc"
    # Resolution anchors on the same key.
    assert find_player_character([{"name": "李", "role": "npc"}], "李")["name"] == "李"
    assert (
        find_player_character([{"name": "0-imposter", "role": "player"}], "李") is None
    )
