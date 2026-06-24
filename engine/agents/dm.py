"""DM agent — generates narrative in response to player actions.

Wraps the OpenAI chat completion call in two flavors:

- ``run_turn``: blocking, returns a complete ``DMTurnResult`` once the
  LLM finishes generating
- ``stream_turn``: a plain generator yielding token strings as they
  arrive, so the caller can forward them to an SSE response while the
  DM is still thinking

Both build their prompt from a ``DMTurnInput`` (session context +
player action) using ``engine.prompts.dm.DM_SYSTEM_PROMPT`` as the
system message. Neither function calls the Fact-Extractor — the
caller orchestrates ``stream_turn → accumulate → fact_extractor.extract
→ dispatch.apply_world_update`` in whatever order the transport
requires.

Design decisions
----------------
**No Fact-Extractor call inside the DM.** Separation of concerns:
``run_turn`` returns a ``DMTurnResult`` with ``world_update_payload=None``
always. Callers that care about the structured payload run
``fact_extractor.extract(result.raw_response, ...)`` themselves. This
keeps the DM agent single-purpose (text in, text out) and lets the
FastAPI SSE handler decide when to parse the payload — typically
after the stream closes, so parsing latency does not delay tokens
reaching the player.

**Streaming is a plain generator, not a framework object.**
``stream_turn`` yields ``str`` values. The caller wraps the generator
in a ``StreamingResponse``, an SSE event stream, a pytest assertion
loop, or anything else. The engine does not know or care about
transport.

**Client injection via keyword-only argument.** Production code calls
``run_turn(config, input)`` / ``stream_turn(config, input)`` and gets
a fresh OpenAI client built from the config. Tests pass
``client=FakeOpenAI(...)`` to inject a stub that matches the SDK's
``.chat.completions.create`` shape without hitting the network. This
is the same pattern as ``engine.dispatch.fs_manager.apply_world_update``.

**``_build_messages`` is private.** It ports the prompt-assembly logic
out of ``backend/api/dm_ai.py`` but operates on the engine's
``WorldContext`` dataclass instead of the Django dict shape. It is
module-private because callers do not need to call it — they build a
``WorldContext`` and hand it to ``run_turn``/``stream_turn``, and the
message assembly happens internally.

**``build_world_context`` stays in the caller.** The engine deliberately
does not know how to load state from anywhere. The caller (today
``backend/api/``, tomorrow the new FastAPI backend) is responsible for
producing a ``WorldContext`` from whatever ground truth it reads. Under
ADR 0001 that ground truth is ``data/state/*.json``; the engine does
not care.
"""

import re
from typing import Any, Iterator

from ..llm import build_client
from ..modules import build_dm_prompt
from ..types import Config, DMTurnInput, DMTurnResult, IntroInput, WorldContext

# Strip a trailing <world_update>...</world_update> block from raw DM
# output before returning the user-facing narrative. Mirrors the
# Fact-Extractor's extraction regex so both see the same blocks.
_WORLD_UPDATE_BLOCK = re.compile(r"<world_update>[\s\S]*?</world_update>")


def run_turn(
    config: Config,
    turn_input: DMTurnInput,
    *,
    client: Any | None = None,
) -> DMTurnResult:
    """Run a blocking DM turn and return the complete result.

    The returned ``DMTurnResult.narrative`` is the player-facing text
    with any trailing ``<world_update>`` block stripped. The raw LLM
    response (with the block preserved) is available as
    ``DMTurnResult.raw_response`` for the Fact-Extractor to consume.

    ``world_update_payload`` is always ``None`` — this function does not
    call the Fact-Extractor. See the module docstring for why.

    Parameters
    ----------
    config
        Engine configuration. ``openai_api_key``, ``openai_base_url``,
        ``dm_model``, and ``max_completion_tokens`` are used.
    turn_input
        Session context plus the player's latest action.
    client
        Optional OpenAI-SDK-compatible client for test injection.
        Production callers should omit this and let the function
        build a client from ``config``.
    """
    if client is None:
        client = build_client(config)

    messages = _build_messages(
        turn_input.world_context,
        turn_input.player_action,
        turn_input.roll,
        turn_input.level_up,
    )

    response = client.chat.completions.create(
        model=config.dm_model,
        messages=messages,
        max_completion_tokens=config.max_completion_tokens,
    )
    raw = (response.choices[0].message.content or "") if response.choices else ""
    narrative = _strip_world_update(raw)

    return DMTurnResult(
        narrative=narrative,
        raw_response=raw,
        world_update_payload=None,
    )


def stream_turn(
    config: Config,
    turn_input: DMTurnInput,
    *,
    client: Any | None = None,
) -> Iterator[str]:
    """Stream a DM turn token-by-token.

    Yields each token as it arrives from the LLM. Callers accumulate
    tokens into a full response (the ``<world_update>`` block is
    usually at the end, so it arrives last), and after the generator
    is exhausted they pass the accumulated raw text to
    ``engine.agents.fact_extractor.extract`` to produce the
    ``apply_world_update`` payload.

    Typical usage in an SSE handler:

        full = []
        for token in stream_turn(config, turn_input):
            full.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\\n\\n"

        raw = "".join(full)
        result = fact_extractor.extract(raw, session_id, turn_number)
        if result.payload is not None:
            dispatch.apply_world_update(config, result.payload)

    Parameters
    ----------
    config
        Engine configuration.
    turn_input
        Session context plus the player's latest action.
    client
        Optional OpenAI-SDK-compatible client for test injection.
    """
    if client is None:
        client = build_client(config)

    messages = _build_messages(
        turn_input.world_context,
        turn_input.player_action,
        turn_input.roll,
        turn_input.level_up,
    )

    stream = client.chat.completions.create(
        model=config.dm_model,
        messages=messages,
        max_completion_tokens=config.max_completion_tokens,
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        token = getattr(delta, "content", None) or ""
        if token:
            yield token


def generate_intro(
    config: Config,
    intro_input: IntroInput,
    *,
    client: Any | None = None,
) -> DMTurnResult:
    """Run a session-intro turn and return the complete result.

    Unlike ``run_turn``/``stream_turn`` (which build their user
    message from the current world context + player action), the
    intro turn uses a different user message that tells the LLM to
    establish a new world from scratch: introduce NPCs, seed
    locations, and open with an immediate situation for the player
    to respond to.

    The returned ``DMTurnResult.raw_response`` includes a
    ``<world_update>`` block establishing the initial state, which
    the caller passes to the Fact-Extractor to produce the initial
    ``apply_world_update`` payload for fs-manager.

    Parameters
    ----------
    config
        Engine configuration.
    intro_input
        World name, player character, optional seed. When the seed
        is None, the DM is given a fallback "classic dark fantasy"
        framing matching the existing backend behavior.
    client
        Optional OpenAI-SDK-compatible client for test injection,
        same pattern as ``run_turn``.
    """
    if client is None:
        client = build_client(config)

    messages = _build_intro_messages(intro_input)

    response = client.chat.completions.create(
        model=config.dm_model,
        messages=messages,
        max_completion_tokens=config.max_completion_tokens,
    )
    raw = (response.choices[0].message.content or "") if response.choices else ""
    narrative = _strip_world_update(raw)

    return DMTurnResult(
        narrative=narrative,
        raw_response=raw,
        world_update_payload=None,
    )


# ── helpers ──────────────────────────────────────────────────────────


def _strip_world_update(raw: str) -> str:
    """Return the raw DM response with any <world_update> block removed."""
    return _WORLD_UPDATE_BLOCK.sub("", raw).strip()


def _build_messages(
    ctx: WorldContext,
    player_action: str,
    roll: dict | None = None,
    level_up: dict | None = None,
) -> list[dict]:
    """Assemble the OpenAI ``messages`` array for a DM turn.

    Ported from the Django ``backend/api/dm_ai.py``'s ``build_messages``
    but operates on the engine's ``WorldContext`` dataclass rather than
    a plain dict. Produces a two-message list: the DM system prompt
    followed by a single user message containing the current world
    context block plus the player's action. When ``roll`` is supplied
    (ADR-0005 resolution module), a structured ROLL RESULT block is
    appended so the DM resolves from the margin.
    """
    chars = (
        ", ".join(
            f"{c.get('name', '?')} ({c.get('role', '?')}, {c.get('status', '?')})"
            for c in ctx.characters
        )
        or "None yet"
    )
    locs = ", ".join(loc.get("name", "?") for loc in ctx.locations) or "None yet"
    facs = (
        ", ".join(
            f"{f.get('name', '?')} (relation: {f.get('playerRelation', 0)})"
            for f in ctx.factions
        )
        or "None yet"
    )
    item_list = (
        ", ".join(
            (
                f"{i.get('name', '?')} (owned by {i['ownedBy']})"
                if i.get("ownedBy")
                else i.get("name", "?")
            )
            for i in ctx.items
        )
        or "None yet"
    )
    recent = (
        "\n\n".join(
            f"Player: {t.get('playerAction', '')}\nDM: {t.get('narrative', '')}"
            for t in ctx.recent_turns[-3:]
        )
        or "This is the beginning of the session."
    )

    context_block = (
        f"\nCURRENT WORLD STATE:\n"
        f"- World: {ctx.world_name} ({ctx.current_era})\n"
        f"- Location: {ctx.current_location}\n"
        f"- Time: {ctx.time_of_day}, Weather: {ctx.weather}\n"
        f"- Tension: {ctx.tension}/10\n\n"
        f"KNOWN CHARACTERS: {chars}\n"
        f"KNOWN LOCATIONS: {locs}\n"
        f"KNOWN FACTIONS: {facs}\n"
        f"ITEMS IN PLAY: {item_list}\n\n"
        f"RECENT TURNS:\n{recent}\n"
    )

    user_content = (
        context_block
        + "\nPLAYER ACTION: "
        + player_action
        + _roll_block(roll)
        + _level_up_block(level_up)
    )

    return [
        # ADR-0005: the system prompt is assembled from the world's active
        # module set. With the default (base-only) set this is byte-identical
        # to the former DM_SYSTEM_PROMPT constant.
        {"role": "system", "content": build_dm_prompt(ctx.modules)},
        {"role": "user", "content": user_content},
    ]


def _level_up_block(level_up: dict | None) -> str:
    """Render a progression-module LEVEL-UP CHOICE block (RFC-0009), or ""
    when the turn carries no level-up. The player has chosen which stat to
    raise; the DM applies exactly that (the PC-ownership wall). Tolerant of
    a missing stat (degrades to "" rather than instructing a bad apply)."""
    if not isinstance(level_up, dict):
        return ""
    stat = level_up.get("stat")
    if not isinstance(stat, str) or not stat:
        return ""
    to_level = level_up.get("to_level")
    lvl = f" to level {to_level}" if to_level is not None else ""
    return (
        f"\n\nLEVEL-UP CHOICE: the player advances{lvl} and chooses to raise "
        f"{stat}. Apply the level-up package exactly as chosen (raise only "
        f"{stat})."
    )


def _roll_block(roll: dict | None) -> str:
    """Render a resolution-module ROLL RESULT block for the user message,
    or "" when the turn carries no roll (ADR-0005 / RFC-0006). Structured,
    labeled fields — the DM resolves from the margin and never re-rolls or
    invents the number. Tolerant of missing keys (a malformed roll degrades
    to whatever fields are present rather than raising)."""
    if not isinstance(roll, dict) or not roll:
        return ""
    # `effect_die` / `effect_roll` ride along on a combat attack (RFC-0007):
    # the frontend rolls the weapon die client-side; the DM computes
    # damage = effect_roll + floor(margin/10).
    fields = (
        "stat",
        "rolled",
        "bonus",
        "total",
        "target",
        "margin",
        "open_ended",
        "effect_die",
        "effect_roll",
    )
    lines = [f"- {k}: {roll[k]}" for k in fields if k in roll]
    if not lines:
        return ""
    return (
        "\n\nROLL RESULT (resolve the action from this; do not re-roll):\n"
        + "\n".join(lines)
    )


_INTRO_SEED_FALLBACK = "Create a classic dark fantasy setting with mystery and danger."


def _build_intro_messages(intro: IntroInput) -> list[dict]:
    """Assemble the OpenAI ``messages`` array for a session-intro turn.

    Operates on the engine's ``IntroInput`` dataclass. Produces a
    two-message list: the shared DM system prompt followed by a user
    message that tells the LLM to establish a new world.

    World Generation Layer 1: if any of the optional creation-context
    fields (genre, tone, starting_region, persona_id, mood, sandbox,
    permadeath) are set, append a "CREATION CONTEXT" block listing
    only the fields the player actually specified. The DM sees them
    as free-form strings and can anchor the opening to them.

    World Generation Layer 2: if any of the ``*_prompt`` fields are
    set, prepend a "WORLD FOUNDATIONS" block of authored preset
    content (multi-sentence paragraphs loaded by the backend from
    ``data/lore/core/presets/``). The paragraphs go in as standalone
    blocks, not one-line bullets, so the LLM treats them as setting
    material rather than label metadata. When a ``*_prompt`` is
    present, ``_creation_context_lines`` omits the corresponding
    bare bullet so the same information does not appear twice.
    """
    seed_context = intro.world_seed if intro.world_seed else _INTRO_SEED_FALLBACK

    user_content = (
        f"Begin a new RPG session with these parameters:\n"
        f"- World Name: {intro.world_name}\n"
        f"- Player Character: {intro.player_name}, a {intro.player_class}\n"
        f"- {seed_context}\n"
    )

    preset_block = _format_preset_block(intro)
    if preset_block:
        user_content += (
            "\nWORLD FOUNDATIONS (authored preset content — treat as "
            "canonical setting material):\n\n"
        )
        user_content += preset_block
        user_content += "\n"

    creation_lines = _creation_context_lines(intro)
    if creation_lines:
        user_content += (
            "\nCREATION CONTEXT (player choices — honor them in the opening):\n"
        )
        user_content += "\n".join(f"- {line}" for line in creation_lines)
        user_content += "\n"

    user_content += (
        "\nOpen the story with an atmospheric introduction. Set the scene, "
        "establish the world, introduce at least 2 NPCs and 2 locations. "
        "Give the player an immediate situation to respond to.\n\n"
        "Create a compelling opening that establishes the tone and immediately draws the player in."
    )

    return [
        # ADR-0005: assemble from the intro's module set (default base-only).
        {"role": "system", "content": build_dm_prompt(intro.modules)},
        {"role": "user", "content": user_content},
    ]


def _creation_context_lines(intro: IntroInput) -> list[str]:
    """Return one prompt line per populated creation-context field.

    Skips fields the player didn't set so the intro prompt stays
    terse for callers that pre-date Layer 1. Booleans are only
    emitted when True — the default (False) means "player didn't
    opt into this mode."

    Layer 2 suppression rule: when a field has a corresponding
    ``*_prompt`` set on the IntroInput, the bare label line is
    omitted here so the WORLD FOUNDATIONS block (a full paragraph
    of authored preset content) carries the information alone. The
    four paired fields are:
    - ``genre`` / ``genre_prompt``
    - ``starting_region`` / ``region_prompt``
    - (``persona_name`` or ``persona_id``) / ``persona_prompt``
    - ``mood`` / ``mood_prompt``
    ``tone``, ``sandbox``, and ``permadeath`` are always label-only
    (no preset counterpart) because they are modifiers rather than
    content bundles.

    Persona formatting (Layer 1.5): when ``persona_name`` is present,
    the line reads ``"DM persona: <name> — <description>"`` (or just
    ``"DM persona: <name>"`` when no description is supplied). When
    only ``persona_id`` is present, falls back to ``"DM persona: <id>"``
    so pre-Layer-1.5 callers and tests continue to work. Delegated
    to the ``_format_persona_line`` helper.
    """
    lines: list[str] = []
    if intro.genre and not intro.genre_prompt:
        lines.append(f"Genre: {intro.genre}")
    if intro.tone:
        lines.append(f"Tone: {intro.tone}")
    if intro.starting_region and not intro.region_prompt:
        lines.append(f"Starting region: {intro.starting_region}")
    if not intro.persona_prompt:
        persona_line = _format_persona_line(intro)
        if persona_line:
            lines.append(persona_line)
    if intro.mood and not intro.mood_prompt:
        lines.append(f"DM mood: {intro.mood}")
    if intro.sandbox:
        lines.append("Sandbox mode: the player prefers an open, non-linear world")
    if intro.permadeath:
        lines.append(
            "Permadeath mode: the player has opted into permanent character death — consequences are real"
        )
    return lines


def _format_preset_block(intro: IntroInput) -> str:
    """Return the WORLD FOUNDATIONS paragraph block for Layer 2 presets.

    When any of ``genre_prompt`` / ``region_prompt`` / ``persona_prompt``
    / ``mood_prompt`` are set on the IntroInput, format each as a
    standalone paragraph under an uppercase header (e.g. ``GENRE:``).
    Paragraphs are joined with a blank line so the LLM sees them as
    distinct setting blocks. Returns an empty string when no preset
    fields are set so the caller can cleanly skip the whole section.

    Ordering is deliberate: genre first (sets the overall world
    frame), starting region second (anchors the opening scene to a
    specific place), persona third (voice/tone for narration), mood
    last (the finest-grained modifier, meant to colour the prior
    blocks rather than replace them).
    """
    fragments: list[str] = []
    if intro.genre_prompt:
        fragments.append(f"GENRE:\n{intro.genre_prompt.strip()}")
    if intro.region_prompt:
        fragments.append(f"STARTING REGION:\n{intro.region_prompt.strip()}")
    if intro.persona_prompt:
        fragments.append(f"DM PERSONA:\n{intro.persona_prompt.strip()}")
    if intro.mood_prompt:
        fragments.append(f"MOOD:\n{intro.mood_prompt.strip()}")
    return "\n\n".join(fragments)


def _format_persona_line(intro: IntroInput) -> str | None:
    """Compose the DM persona line from whatever persona fields are set.

    Cases (in priority order — `persona_name` wins over `persona_id`
    so a Layer-1.5 caller never gets stuck on the bare-id fallback):

    1. ``persona_name`` and ``persona_description`` both set →
       ``"DM persona: <name> — <description>"``. The full description
       is passed through unchanged — frontend descriptions are
       single-sentence today (see ``MOCK_PERSONAS`` in
       ``WorldCreation.jsx``) so there is no truncation.
    2. ``persona_name`` set, ``persona_description`` missing →
       ``"DM persona: <name>"``. Less ideal than case 1 but still
       better than the opaque id, since at least the LLM gets a
       human-readable label.
    3. Only ``persona_id`` set → ``"DM persona: <id>"``. The
       pre-Layer-1.5 fallback. Pre-existing tests and any caller
       that hasn't been updated to send the descriptive fields land
       here.
    4. Neither ``persona_name`` nor ``persona_id`` set → return
       ``None`` so the caller skips the persona line entirely.
       (Note: this fires even if ``persona_description`` happens to
       be set on its own — a description without a name has nothing
       to anchor to, so it's treated the same as nothing being set.)
    """
    if intro.persona_name:
        if intro.persona_description:
            return f"DM persona: {intro.persona_name} — {intro.persona_description}"
        return f"DM persona: {intro.persona_name}"
    if intro.persona_id:
        return f"DM persona: {intro.persona_id}"
    return None
