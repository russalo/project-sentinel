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
from ..prompts.dm import DM_SYSTEM_PROMPT
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

    messages = _build_messages(turn_input.world_context, turn_input.player_action)

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

    messages = _build_messages(turn_input.world_context, turn_input.player_action)

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


def _build_messages(ctx: WorldContext, player_action: str) -> list[dict]:
    """Assemble the OpenAI ``messages`` array for a DM turn.

    Ported from the Django ``backend/api/dm_ai.py``'s ``build_messages``
    but operates on the engine's ``WorldContext`` dataclass rather than
    a plain dict. Produces a two-message list: the DM system prompt
    followed by a single user message containing the current world
    context block plus the player's action.
    """
    chars = (
        ", ".join(
            f"{c.get('name', '?')} ({c.get('role', '?')}, {c.get('status', '?')})"
            for c in ctx.characters
        )
        or "None yet"
    )
    locs = (
        ", ".join(l.get("name", "?") for l in ctx.locations) or "None yet"
    )
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

    return [
        {"role": "system", "content": DM_SYSTEM_PROMPT},
        {"role": "user", "content": context_block + "\nPLAYER ACTION: " + player_action},
    ]


_INTRO_SEED_FALLBACK = "Create a classic dark fantasy setting with mystery and danger."


def _build_intro_messages(intro: IntroInput) -> list[dict]:
    """Assemble the OpenAI ``messages`` array for a session-intro turn.

    Ported from the Django backend's ``generate_world_intro`` but
    operates on the engine's ``IntroInput`` dataclass. Produces a
    two-message list: the shared DM system prompt followed by a
    user message that tells the LLM to establish a new world.
    """
    seed_context = intro.world_seed if intro.world_seed else _INTRO_SEED_FALLBACK

    user_content = (
        f"Begin a new RPG session with these parameters:\n"
        f"- World Name: {intro.world_name}\n"
        f"- Player Character: {intro.player_name}, a {intro.player_class}\n"
        f"- {seed_context}\n\n"
        f"Open the story with an atmospheric introduction. Set the scene, "
        f"establish the world, introduce at least 2 NPCs and 2 locations. "
        f"Give the player an immediate situation to respond to.\n\n"
        f"Create a compelling opening that establishes the tone and immediately draws the player in."
    )

    return [
        {"role": "system", "content": DM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
