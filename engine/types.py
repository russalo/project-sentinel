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
    # RFC-0010: the day counter the time module advances on a night wrap /
    # long rest. Carried into the DM context each turn so the DM sees the
    # current value and increments (rather than guesses/resets) it.
    day: int = 1
    characters: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    factions: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    # ADR-0005 / RFC-0005: the world's active module set
    # ``{subsystem: module_name}``. ``None`` → the engine assembles the
    # DM prompt from the default (base-only) module set, identical to
    # pre-RFC-0005 behavior. The backend populates this from the world's
    # ``state.json`` ``modules`` field (lazy-defaulted when absent).
    modules: dict[str, str] | None = None


@dataclass
class DMTurnInput:
    """Input to a single DM turn."""

    session_id: str
    player_action: str
    world_context: WorldContext
    # ADR-0005 resolution module (RFC-0006 Slice 2): when the player is
    # resolving a previously-requested check, the frontend's d100 roll
    # result rides here as ``{stat, rolled, bonus, total, target, margin,
    # open_ended}``. None on an ordinary turn. The DM agent renders it as
    # a structured ROLL RESULT block in the prompt so the DM resolves from
    # the margin (never re-rolls, never invents the number).
    roll: dict[str, object] | None = None
    # ADR-0005 progression module (RFC-0009): when the player enacts a
    # DM-proposed level-up, their chosen stat rides here as
    # ``{"stat": "will", "to_level": 2}``. None otherwise. Rendered as a
    # LEVEL-UP CHOICE block so the DM applies exactly the player's choice
    # (the PC-ownership wall — the DM never picks the stat itself).
    level_up: dict[str, object] | None = None


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
    opening to the player's choices. These are free-form strings
    passed straight through when no preset content is resolved.

    World Generation Layer 2 (preset content framework) adds four
    optional ``*_prompt`` fields: ``genre_prompt``, ``persona_prompt``,
    ``mood_prompt``, and ``region_prompt``. When set, they carry
    multi-sentence authored content loaded by the backend from
    ``data/lore/core/presets/`` and are injected into the intro
    prompt as standalone paragraphs (not one-line bullets). When a
    ``*_prompt`` field is set, ``_creation_context_lines`` omits the
    corresponding bare label line so the prompt is not redundant.
    The distinction is an intentional separation between "the player
    picked this label" (bare field, Layer 1) and "here is the real
    content behind that label" (prompt field, Layer 2). Tone,
    sandbox, and permadeath remain label-only since they are
    modifiers rather than content bundles.
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

    # Layer 2 preset-content fields. Each carries a multi-sentence
    # paragraph authored under data/lore/core/presets/<type>/<id>.toml
    # and loaded by the backend's ``presets.load_preset`` helper. The
    # engine does not load them itself — it only knows how to format
    # them into the intro prompt. When None (the common case for
    # pre-Layer-2 callers and tests), the bare label fields above
    # are used instead, preserving backward compatibility.
    genre_prompt: str | None = None
    persona_prompt: str | None = None
    mood_prompt: str | None = None
    region_prompt: str | None = None

    # ADR-0005 / RFC-0005: the world's active module set for the intro
    # turn. ``None`` → default (base-only) module set, identical to
    # pre-RFC-0005 behavior.
    modules: dict[str, str] | None = None


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
