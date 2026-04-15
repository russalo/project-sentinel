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

    The engine package does not read `os.environ` — callers (e.g. the
    backend adapter) assemble this from their own settings and hand it in.

    MCP Bridge URLs default to the local dev layout used by `just start`
    (fs-manager on :8010, git-sync on :8012). Production or Tailscale-mesh
    deployments override these.
    """

    openai_api_key: str
    openai_base_url: str | None = None
    dm_model: str = "gpt-4o-mini"
    max_completion_tokens: int = 2000

    fs_manager_url: str = "http://127.0.0.1:8010"
    git_sync_url: str = "http://127.0.0.1:8012"


@dataclass
class WorldContext:
    """Snapshot of the current world state passed into a DM turn.

    This is the engine's view of the world — a flat, framework-agnostic
    representation. The caller loads it from wherever ground truth lives
    (``data/state/*.json`` per ADR 0001).
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
class IntroInput:
    """Input to a session-intro turn.

    The intro turn uses a different system-prompt framing than a
    normal turn — the LLM is told to establish a new world, introduce
    NPCs and locations, and give the player an immediate situation to
    respond to. See `engine.agents.dm.generate_intro`.

    The ``genre``/``tone``/``starting_region``/``persona_id``/``mood``/
    ``sandbox``/``permadeath`` fields are optional World Generation
    Layer 1 inputs — when any of them are set, the intro prompt
    appends a "CREATION CONTEXT" block so the LLM can anchor its
    opening to the player's choices. No preset lookups happen yet;
    these are free-form strings passed straight through.
    """

    world_name: str
    player_name: str
    player_class: str
    world_seed: str | None = None

    genre: str | None = None
    tone: str | None = None
    starting_region: str | None = None
    persona_id: str | None = None
    # Layer 1.5 (persona resolution): the backend receives persona_name
    # and persona_description alongside persona_id and threads them
    # through to the intro prompt. When both are present,
    # _creation_context_lines formats the persona line as
    # ``"DM persona: <name> — <description>"`` instead of the opaque id.
    # Optional so callers that only have an id still work — they get
    # the ``"DM persona: <id>"`` fallback.
    persona_name: str | None = None
    persona_description: str | None = None
    mood: str | None = None
    sandbox: bool = False
    permadeath: bool = False


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
