"""Pydantic request/response models for the FastAPI backend.

These mirror the JSON shapes the Django backend served so the frontend
doesn't need to change. Field aliases handle the snake_case → camelCase
conversion the frontend expects (e.g. ``player_character_name`` →
``playerCharacterName``).

Only the models actually used by the frontend are defined. The Django
backend had extra response models for read endpoints (``/api/world``,
``/api/characters``, etc.) that the frontend never called — those are
omitted here per the frontend-contract verification done before
writing this file.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _CamelModel(BaseModel):
    """Base model that serializes snake_case fields as camelCase.

    The frontend's fetch-and-stream code reads JSON with camelCase
    keys (``sessionId``, ``playerAction``, ``worldName``). Pydantic's
    alias generator handles the translation both ways.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda s: "".join(
            [s.split("_")[0]] + [w.capitalize() for w in s.split("_")[1:]]
        ),
    )


# ── POST /api/session/new ────────────────────────────────────────────


class NewSessionRequest(_CamelModel):
    world_name: str = Field(default="The Shattered Realm")
    player_character_name: str = Field(default="Traveler")
    player_character_class: str = Field(default="Adventurer")
    world_seed: str | None = None

    # World Generation — Layer 1 fields. The frontend's WorldCreation
    # flow collects these from the user and (as of this change) sends
    # them through. Currently consumed only as free-form context in the
    # intro prompt — no preset lookups, no mechanical effects. The
    # eventual genre/persona/mood preset system will replace the
    # free-form handling with structured content bundles under
    # data/{lore,state}/core/presets/.
    genre: str | None = None
    tone: str | None = None
    starting_region: str | None = None
    persona_id: str | None = None
    # Layer 1.5: persona_name + persona_description let the frontend
    # resolve its mock persona catalog to descriptive text the DM
    # intro prompt can actually use. Without these, the LLM sees only
    # the opaque persona_id string and doesn't know what "oracle"
    # means. When the real preset system lands (BACKLOG: DM Personas
    # & Content Framework), the backend will resolve from
    # data/lore/core/presets/personas/ directly and these two fields
    # drop out of the request contract. Optional so legacy/test
    # payloads still validate.
    persona_name: str | None = None
    persona_description: str | None = None
    mood: str | None = None
    sandbox: bool = False
    permadeath: bool = False


class TurnResponse(_CamelModel):
    id: int
    session_id: str
    turn_number: int
    player_action: str
    narrative: str
    world_updates: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class NewSessionResponse(_CamelModel):
    session_id: str
    world_id: str
    turns: list[TurnResponse]
    started_at: str
    world_name: str
    # ADR 0003 Slice A — per-world session token. ``None`` when token
    # enforcement is off (no secret configured); the client stores it keyed by
    # world_id and sends it as ``X-Sentinel-World-Token`` on world-scoped calls.
    session_token: str | None = None


# ── POST /api/stream ─────────────────────────────────────────────────


class RollResult(_CamelModel):
    """A d100 check result (ADR-0005 resolution module / RFC-0006).

    Rolled client-side (real randomness, not LLM bias) and sent on the
    *resolve* turn so the DM resolves the action from the margin. The
    frontend sends camelCase (``openEnded``); ``model_dump()`` yields the
    snake-case keys the engine's ROLL RESULT block reads.
    """

    stat: str
    rolled: int = Field(ge=1, le=100)
    bonus: int
    total: int
    target: int
    margin: int
    # "high" (open-ended surge), "low" (fumble spiral), or None.
    open_ended: str | None = None
    # RFC-0014: which kind of check this resolves. The frontend echoes back the
    # check_request's `kind`. Pattern-constrained (like effect_die / level_up
    # stat) because it is client-controlled and steers engine logic — a
    # "death_save" routes to engine-authoritative outcome + server-recomputed
    # margin, so an unconstrained string can't smuggle in a new branch. Default
    # "skill" = an ordinary DM-resolved check.
    kind: str = Field(default="skill", pattern=r"^(skill|death_save)$")
    # RFC-0007 combat / RFC-0008 magic: on an attack or contested cast the
    # frontend also rolls the magnitude die (weapon or spell) named by the
    # check_request's effect_die. None otherwise. `model_dump()` yields
    # snake-case (effect_die / effect_roll).
    #
    # effect_die is pattern-constrained to a "<n>d<m>" die spec — it lands
    # verbatim in the DM's ROLL RESULT prompt block, so an unconstrained
    # client string would be a prompt-injection vector (gemini security-high
    # on PR #149). effect_roll is bounded 1..100 (no die exceeds it) so a
    # crafted client can't inflate damage/healing (gemini security-medium,
    # PR #148). The roll is client-side, so bound what feeds the effect.
    effect_die: str | None = Field(default=None, pattern=r"^\d{1,2}d\d{1,3}$")
    effect_roll: int | None = Field(default=None, ge=1, le=100)


class LevelUpChoice(_CamelModel):
    """The player's level-up enactment (ADR-0005 progression / RFC-0009).

    Sent on the turn where the player takes a DM-proposed level-up: the
    attribute they chose to raise (+ the target level for clarity). The
    DM applies exactly this — the PC-ownership wall (the DM proposes,
    never picks the stat itself)."""

    # one of body / mind / heart / will. Pattern-constrained because it
    # lands verbatim in the engine's LEVEL-UP CHOICE prompt block — an
    # unconstrained client string would be a prompt-injection vector (the
    # same class as RollResult.effect_die; gemini security-high / codex P2,
    # PR #150). The frontend only ever sends one of the four.
    stat: str = Field(pattern=r"^(body|mind|heart|will)$")
    # bounded to the progression module's v0.1 1..5 cap so a crafted or
    # malformed turn can't render "level 999" into the prompt; the bound
    # tracks the module cap and rises when it does.
    to_level: int | None = Field(default=None, ge=1, le=5)


class StreamRequest(_CamelModel):
    action: str
    session_id: str
    # Optional, advisory only. The backend does NOT route on this — it locates
    # the session's own world tree authoritatively from the session_id
    # (find_session_data_dir), so a client need not send world_id and a wrong
    # one can't mis-route a read. Kept for forward-compat: Slice 4's
    # /w/<world_id> frontend routing carries it in the URL, and it's useful for
    # telemetry. (ADR 0002 Slice 3.)
    world_id: str | None = None
    # ADR-0005 resolution module (RFC-0006 Slice 2): present on a *resolve*
    # turn — the d100 result for a check the DM previously requested. None on
    # an ordinary turn.
    roll: RollResult | None = None
    # ADR-0005 progression module (RFC-0009): present when the player enacts
    # a DM-proposed level-up — their chosen stat. None otherwise.
    level_up: LevelUpChoice | None = None


# ── GET /healthz ─────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
