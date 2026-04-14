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
    turns: list[TurnResponse]
    started_at: str
    world_name: str


# ── POST /api/stream ─────────────────────────────────────────────────


class StreamRequest(_CamelModel):
    action: str
    session_id: str


# ── GET /healthz ─────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
