"""Type contracts for the engine package.

All public engine APIs consume and return these types. They are plain
dataclasses — no Django models, no ORM coupling, no hidden state. The
caller is responsible for translating between these types and whatever
storage layer happens to hold ground truth.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Config:
    """Runtime configuration. Callers build this and pass it to engine entry points.

    The engine package does not read `os.environ` — callers (e.g. the Django
    adapter in backend/) assemble this from their own settings and hand it in.
    """

    openai_api_key: str
    openai_base_url: str | None = None
    dm_model: str = "gpt-4o-mini"
    max_completion_tokens: int = 2000


@dataclass
class WorldContext:
    """Snapshot of the current world state passed into a DM turn.

    This is the engine's view of the world — a flat, framework-agnostic
    representation. The caller loads it from wherever ground truth lives
    (Postgres today; possibly data/state/*.json later).
    """

    world_name: str
    current_era: str
    current_location: str
    weather: str
    time_of_day: str
    tension: int
    characters: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    factions: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    recent_turns: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DMTurnInput:
    """Input to a single DM turn."""

    session_id: str
    player_action: str
    world_context: WorldContext


@dataclass
class DMTurnResult:
    """Result of a completed DM turn.

    `narrative` is the player-facing story beat with any embedded
    <world_update> block stripped out.

    `raw_response` is the full LLM response, preserved so the Fact-Extractor
    can parse it independently of the narrative stripping.

    `world_update_payload` is the schema-valid apply_world_update payload
    produced by the Fact-Extractor, or None if extraction was skipped or
    failed. Callers that care about consistency should validate it via
    `engine.validate()` before dispatch.
    """

    narrative: str
    raw_response: str
    world_update_payload: dict[str, Any] | None
