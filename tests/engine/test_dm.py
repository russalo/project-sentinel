"""Unit tests for engine.agents.dm.run_turn and stream_turn.

Tests inject fake OpenAI clients that match the subset of the SDK
surface the DM agent uses (``.chat.completions.create`` returning
either a completion-like object or an iterable of chunk-like objects).
No real network, no API keys, no httpx.

The helpers below construct the minimum object shape the engine code
actually touches. They intentionally do NOT mirror the full OpenAI
SDK — if the DM agent starts reading new fields, the helpers will
need updating, and that's the right signal.
"""

from dataclasses import dataclass
from typing import Any

import pytest

from engine.agents import dm as dm_agent
from engine.agents.dm import (
    _build_intro_messages,
    _build_messages,
    _creation_context_lines,
    _format_preset_block,
    _strip_world_update,
    generate_intro,
    run_turn,
    stream_turn,
)
from engine.prompts.dm import DM_SYSTEM_PROMPT
from engine.types import Config, DMTurnInput, DMTurnResult, IntroInput, WorldContext


# ── fake OpenAI client plumbing ─────────────────────────────────────


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]


@dataclass
class _FakeDelta:
    content: str | None


@dataclass
class _FakeStreamChoice:
    delta: _FakeDelta


@dataclass
class _FakeStreamChunk:
    choices: list[_FakeStreamChoice]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._response_text: str = ""
        self._stream_tokens: list[str | None] = []

    def set_blocking_response(self, text: str) -> None:
        self._response_text = text

    def set_stream_tokens(self, tokens: list[str | None]) -> None:
        self._stream_tokens = tokens

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(
                _FakeStreamChunk(
                    choices=[_FakeStreamChoice(delta=_FakeDelta(content=token))]
                )
                for token in self._stream_tokens
            )
        return _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content=self._response_text))]
        )


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def _make_config() -> Config:
    return Config(
        openai_api_key="test-key", dm_model="test-model", max_completion_tokens=1234
    )


def _make_turn_input(player_action: str = "I look around.") -> DMTurnInput:
    ctx = WorldContext(
        world_name="Test Realm",
        current_era="Test Era",
        current_location="The Test Tavern",
        weather="Clear",
        time_of_day="Noon",
        tension=3,
    )
    return DMTurnInput(
        session_id="abc",
        player_action=player_action,
        world_context=ctx,
    )


# ── _build_messages ─────────────────────────────────────────────────


def test_build_messages_returns_system_plus_user_pair():
    ctx = _make_turn_input().world_context
    messages = _build_messages(ctx, "I look around.")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == DM_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"


def test_build_messages_includes_world_state_in_user_message():
    ctx = _make_turn_input().world_context
    messages = _build_messages(ctx, "I order a drink.")
    user_content = messages[1]["content"]
    assert "Test Realm" in user_content
    assert "The Test Tavern" in user_content
    assert "Tension: 3/10" in user_content
    assert "I order a drink." in user_content


def test_build_messages_renders_none_yet_for_empty_collections():
    ctx = WorldContext(
        world_name="Empty",
        current_era="Start",
        current_location="Void",
        weather="Still",
        time_of_day="Dawn",
        tension=0,
    )
    messages = _build_messages(ctx, "Where am I?")
    user_content = messages[1]["content"]
    assert "KNOWN CHARACTERS: None yet" in user_content
    assert "KNOWN LOCATIONS: None yet" in user_content
    assert "KNOWN FACTIONS: None yet" in user_content
    assert "ITEMS IN PLAY: None yet" in user_content
    assert "beginning of the session" in user_content


def test_build_messages_renders_populated_collections():
    ctx = WorldContext(
        world_name="Populated",
        current_era="Age of Test",
        current_location="Plaza",
        weather="Rain",
        time_of_day="Evening",
        tension=7,
        characters=[
            {"name": "Kael", "role": "npc", "status": "alive"},
            {"name": "Mira", "role": "ally", "status": "alive"},
        ],
        locations=[{"name": "Plaza"}, {"name": "Bazaar"}],
        factions=[{"name": "Grey Pact", "playerRelation": -3}],
        items=[
            {"name": "Iron Key", "ownedBy": "Kael"},
            {"name": "Compass"},
        ],
        recent_turns=[
            {
                "playerAction": "Enter the plaza.",
                "narrative": "Rain patters on cobblestone.",
            },
        ],
    )
    messages = _build_messages(ctx, "Greet Kael.")
    user_content = messages[1]["content"]
    assert "Kael (npc, alive)" in user_content
    assert "Mira (ally, alive)" in user_content
    assert "Plaza, Bazaar" in user_content
    assert "Grey Pact (relation: -3)" in user_content
    assert "Iron Key (owned by Kael)" in user_content
    assert "Compass" in user_content
    assert "Rain patters on cobblestone" in user_content
    assert "Greet Kael." in user_content


def test_build_messages_limits_recent_turns_to_last_three():
    ctx = WorldContext(
        world_name="W",
        current_era="E",
        current_location="L",
        weather="w",
        time_of_day="t",
        tension=0,
        recent_turns=[
            {"playerAction": f"action {i}", "narrative": f"narr {i}"} for i in range(10)
        ],
    )
    messages = _build_messages(ctx, "next")
    content = messages[1]["content"]
    assert "action 9" in content
    assert "action 8" in content
    assert "action 7" in content
    assert "action 6" not in content  # only last 3


# ── run_turn ────────────────────────────────────────────────────────


def test_run_turn_returns_dm_turn_result_with_stripped_narrative():
    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response(
        "You step into the tavern, the warmth wrapping around you.\n"
        "<world_update>\n"
        '{"world": {"currentLocation": "Tavern", "tension": 2}}\n'
        "</world_update>"
    )

    result = run_turn(_make_config(), _make_turn_input(), client=client)

    assert isinstance(result, DMTurnResult)
    assert "step into the tavern" in result.narrative
    assert "<world_update>" not in result.narrative
    assert "<world_update>" in result.raw_response
    assert result.world_update_payload is None  # DM does not call Fact-Extractor


def test_run_turn_passes_config_to_client_create_call():
    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response("Some response.")

    run_turn(_make_config(), _make_turn_input(), client=client)

    assert len(client.chat.completions.calls) == 1
    call = client.chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["max_completion_tokens"] == 1234
    assert call.get("stream") in (None, False)


def test_run_turn_handles_empty_completion_gracefully():
    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response("")

    result = run_turn(_make_config(), _make_turn_input(), client=client)
    assert result.narrative == ""
    assert result.raw_response == ""


# ── stream_turn ─────────────────────────────────────────────────────


def test_stream_turn_yields_tokens_in_order():
    client = _FakeOpenAI()
    client.chat.completions.set_stream_tokens(["Hello", ", ", "world", "!"])

    tokens = list(stream_turn(_make_config(), _make_turn_input(), client=client))
    assert tokens == ["Hello", ", ", "world", "!"]


def test_stream_turn_passes_stream_true():
    client = _FakeOpenAI()
    client.chat.completions.set_stream_tokens(["a", "b"])

    list(stream_turn(_make_config(), _make_turn_input(), client=client))
    assert client.chat.completions.calls[0]["stream"] is True


def test_stream_turn_skips_empty_delta_content():
    client = _FakeOpenAI()
    # Some providers emit chunks with content=None (role delta, etc.)
    client.chat.completions.set_stream_tokens(["prelude", None, "middle", "", "tail"])

    tokens = list(stream_turn(_make_config(), _make_turn_input(), client=client))
    assert tokens == ["prelude", "middle", "tail"]


def test_stream_turn_accumulation_round_trips_through_fact_extractor():
    """End-to-end sanity: tokens from stream_turn, joined, include the
    full <world_update> block and can be parsed by the Fact-Extractor.
    This is the integration pattern the FastAPI SSE handler will use."""
    from engine.agents.fact_extractor import extract

    full_response = (
        "The tavern hushes as you enter. The barkeep looks up.\n"
        "<world_update>\n"
        '{"world": {"currentLocation": "The Test Tavern", "tension": 3}}\n'
        "</world_update>"
    )
    # Simulate tokenization by splitting into a few chunks
    tokens = [full_response[i : i + 20] for i in range(0, len(full_response), 20)]

    client = _FakeOpenAI()
    client.chat.completions.set_stream_tokens(tokens)

    accumulated = "".join(
        stream_turn(_make_config(), _make_turn_input(), client=client)
    )
    result = extract(
        accumulated,
        "123e4567-e89b-12d3-a456-426614174000",
        turn_number=1,
    )
    assert result.payload is not None
    assert (
        result.payload["updates"][0]["target_file"]
        == "data/state/core/world/state.json"
    )
    assert "tavern hushes" in result.narrative
    assert "<world_update>" not in result.narrative


# ── _strip_world_update ─────────────────────────────────────────────


def test_strip_world_update_removes_block_and_trims():
    raw = "You swing.\n<world_update>{}</world_update>\n"
    assert _strip_world_update(raw) == "You swing."


def test_strip_world_update_is_noop_when_block_absent():
    raw = "Silence."
    assert _strip_world_update(raw) == "Silence."


# ── client injection default path (without real network) ───────────


def test_run_turn_builds_default_client_when_none_passed(monkeypatch):
    """When client=None, the DM agent calls engine.llm.build_client(config).
    Verify this without hitting the network by stubbing build_client."""
    fake = _FakeOpenAI()
    fake.chat.completions.set_blocking_response("Stubbed.")

    captured: dict[str, Any] = {}

    def fake_build_client(config: Config) -> Any:
        captured["config"] = config
        return fake

    monkeypatch.setattr(dm_agent, "build_client", fake_build_client)

    result = run_turn(_make_config(), _make_turn_input())
    assert result.narrative == "Stubbed."
    assert captured["config"].dm_model == "test-model"


def test_stream_turn_builds_default_client_when_none_passed(monkeypatch):
    fake = _FakeOpenAI()
    fake.chat.completions.set_stream_tokens(["one", "two"])

    def fake_build_client(config: Config) -> Any:
        return fake

    monkeypatch.setattr(dm_agent, "build_client", fake_build_client)

    tokens = list(stream_turn(_make_config(), _make_turn_input()))
    assert tokens == ["one", "two"]


# ── generate_intro ──────────────────────────────────────────────────


def _make_intro_input(world_seed: str | None = None) -> IntroInput:
    return IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        world_seed=world_seed,
    )


def test_build_intro_messages_uses_system_prompt_and_intro_user_message():
    messages = _build_intro_messages(_make_intro_input())
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == DM_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    user = messages[1]["content"]
    assert "The Shattered Expanse" in user
    assert "Kael" in user
    assert "Wanderer" in user
    assert "Begin a new RPG session" in user
    assert "introduce at least 2 NPCs" in user


def test_build_intro_messages_falls_back_to_default_seed_when_none():
    messages = _build_intro_messages(_make_intro_input(world_seed=None))
    user = messages[1]["content"]
    assert "classic dark fantasy" in user.lower()


def test_build_intro_messages_uses_provided_seed_when_given():
    messages = _build_intro_messages(
        _make_intro_input(world_seed="A sunlit desert kingdom")
    )
    user = messages[1]["content"]
    assert "sunlit desert kingdom" in user
    assert "classic dark fantasy" not in user.lower()


def test_build_intro_messages_omits_creation_context_block_when_all_fields_default():
    # Layer 1 creation-context fields are all optional. Callers that
    # pre-date this feature (e.g. any test that constructs IntroInput
    # without them) should produce an intro prompt that never mentions
    # a CREATION CONTEXT block at all.
    messages = _build_intro_messages(_make_intro_input())
    user = messages[1]["content"]
    assert "CREATION CONTEXT" not in user


def test_build_intro_messages_includes_creation_context_block_when_fields_set():
    intro = IntroInput(
        world_name="The Neon Basilica",
        player_name="Iris",
        player_class="Netrunner",
        world_seed=None,
        genre="Cyberpunk",
        tone="Noir",
        starting_region="Lower Terraces",
        persona_id="stern-scholar",
        mood="desperate",
        sandbox=True,
        permadeath=True,
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]

    assert "CREATION CONTEXT" in user
    assert "Genre: Cyberpunk" in user
    assert "Tone: Noir" in user
    assert "Starting region: Lower Terraces" in user
    assert "DM persona: stern-scholar" in user
    assert "DM mood: desperate" in user
    assert "Sandbox mode" in user
    assert "Permadeath mode" in user


def test_build_intro_messages_only_lists_creation_fields_that_are_set():
    # Partial population — genre and tone set, everything else default.
    # The block should appear but only list the fields that were
    # actually specified, not every possible line.
    intro = IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        genre="Fantasy",
        tone="Grimdark",
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]

    assert "CREATION CONTEXT" in user
    assert "Genre: Fantasy" in user
    assert "Tone: Grimdark" in user
    # Fields the test didn't set must not leak into the prompt.
    assert "Starting region:" not in user
    assert "DM persona:" not in user
    assert "DM mood:" not in user
    assert "Sandbox mode" not in user
    assert "Permadeath mode" not in user


def test_build_intro_messages_renders_persona_name_and_description_when_set():
    # Layer 1.5: when the caller provides persona_name and
    # persona_description, the prompt line is "Name — Description"
    # instead of the opaque id. This is what gives the LLM real
    # voice/tone anchoring.
    intro = IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        persona_id="oracle",
        persona_name="Oracle",
        persona_description=(
            "Prophetic and detached. Speaks in fragments and portents; "
            "favors mystery over explanation."
        ),
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]

    assert "CREATION CONTEXT" in user
    # The persona line must include both the name and the description,
    # separated by the em-dash the formatter uses.
    assert (
        "DM persona: Oracle — Prophetic and detached. "
        "Speaks in fragments and portents; favors mystery over explanation."
    ) in user
    # The opaque id must NOT leak through on its own — the descriptive
    # form supersedes it completely so the prompt doesn't carry both.
    assert "DM persona: oracle" not in user


def test_build_intro_messages_falls_back_to_persona_id_when_name_missing():
    # Pre-Layer-1.5 callers (and any test that only sets persona_id)
    # get the old id-only format. This is the backward-compat path
    # that keeps existing _creation_context tests honest.
    intro = IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        persona_id="oracle",
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]

    assert "CREATION CONTEXT" in user
    assert "DM persona: oracle" in user
    # No descriptive form possible — the test doesn't supply one.
    assert " — " not in user.split("DM persona:")[1].split("\n")[0]


def test_generate_intro_returns_dm_turn_result_with_stripped_narrative():
    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response(
        "The Shattered Expanse greets you under a sky of iron clouds.\n"
        "<world_update>\n"
        '{"world": {"currentLocation": "Trog Tavern", "tension": 3}}\n'
        "</world_update>"
    )

    result = generate_intro(_make_config(), _make_intro_input(), client=client)

    assert isinstance(result, DMTurnResult)
    assert "Shattered Expanse" in result.narrative
    assert "<world_update>" not in result.narrative
    assert "<world_update>" in result.raw_response
    assert result.world_update_payload is None


def test_generate_intro_passes_config_model_and_token_limit():
    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response("Intro.")

    generate_intro(_make_config(), _make_intro_input(), client=client)

    assert len(client.chat.completions.calls) == 1
    call = client.chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["max_completion_tokens"] == 1234
    assert call.get("stream") in (None, False)


def test_generate_intro_builds_default_client_when_none_passed(monkeypatch):
    fake = _FakeOpenAI()
    fake.chat.completions.set_blocking_response("Dawn over the wastes.")

    def fake_build_client(config: Config) -> Any:
        return fake

    monkeypatch.setattr(dm_agent, "build_client", fake_build_client)
    result = generate_intro(_make_config(), _make_intro_input())
    assert result.narrative == "Dawn over the wastes."


def test_generate_intro_result_round_trips_through_fact_extractor():
    """End-to-end sanity: an intro response's raw_response carries a
    <world_update> block that the Fact-Extractor can parse into a
    schema-valid payload — same pipeline the FastAPI backend will use
    on POST /api/session/new."""
    from engine.agents.fact_extractor import extract

    client = _FakeOpenAI()
    client.chat.completions.set_blocking_response(
        "The tavern hushes as you enter — weary travelers, a watchful barkeep.\n"
        "<world_update>\n"
        '{"world": {"currentLocation": "Trog Tavern", "tension": 2},'
        ' "characters": [{"name": "Old Maren", "action": "upsert", "role": "npc", "status": "alive"}],'
        ' "locations": [{"name": "Trog Tavern", "action": "upsert", "type": "tavern"}]}\n'
        "</world_update>"
    )

    result = generate_intro(_make_config(), _make_intro_input(), client=client)
    extracted = extract(
        result.raw_response,
        "123e4567-e89b-12d3-a456-426614174000",
        turn_number=0,
    )
    assert extracted.payload is not None
    targets = {u["target_file"] for u in extracted.payload["updates"]}
    assert "data/state/core/world/state.json" in targets
    assert "data/state/core/entities/old_maren.json" in targets
    assert "data/state/core/locations/trog_tavern.json" in targets


# ── Layer 2: preset prompt blocks ──────────────────────────────────


def test_format_preset_block_empty_when_no_prompt_fields():
    intro = _make_intro_input()
    assert _format_preset_block(intro) == ""


def test_format_preset_block_includes_each_set_fragment_as_paragraph():
    intro = IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        genre_prompt="A dark fantasy world of ruin and rumor.",
        region_prompt="The Breach is a wound in the land where the sky bleeds salt.",
        persona_prompt="The Oracle speaks in fragments of futures half-seen.",
        mood_prompt="Ominous stillness. Every silence means something is watching.",
    )
    block = _format_preset_block(intro)
    assert "GENRE:\nA dark fantasy world" in block
    assert "STARTING REGION:\nThe Breach is a wound" in block
    assert "DM PERSONA:\nThe Oracle speaks" in block
    assert "MOOD:\nOminous stillness" in block
    # Ordering: genre → region → persona → mood
    assert block.index("GENRE:") < block.index("STARTING REGION:")
    assert block.index("STARTING REGION:") < block.index("DM PERSONA:")
    assert block.index("DM PERSONA:") < block.index("MOOD:")


def test_format_preset_block_skips_unset_fields():
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        genre_prompt="A dark fantasy world.",
        # persona_prompt / region_prompt / mood_prompt all None
    )
    block = _format_preset_block(intro)
    assert "GENRE:" in block
    assert "STARTING REGION:" not in block
    assert "DM PERSONA:" not in block
    assert "MOOD:" not in block


def test_format_preset_block_strips_surrounding_whitespace():
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        genre_prompt="  \n\nA dark fantasy world.\n\n  ",
    )
    block = _format_preset_block(intro)
    # Stripped — the GENRE: header should be followed directly by the
    # content with no leading whitespace line.
    assert block == "GENRE:\nA dark fantasy world."


def test_build_intro_messages_includes_world_foundations_when_preset_set():
    intro = IntroInput(
        world_name="The Shattered Expanse",
        player_name="Kael",
        player_class="Wanderer",
        genre="fantasy",
        genre_prompt=(
            "A dark fantasy setting of ruin and ancient magic. "
            "Medieval technology, feudal structures, ley lines gone wrong."
        ),
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]
    assert "WORLD FOUNDATIONS" in user
    assert "GENRE:\nA dark fantasy setting" in user
    # The bare "Genre: fantasy" bullet must NOT appear — when the prompt
    # field is set, the label is suppressed to avoid redundancy.
    assert "Genre: fantasy" not in user


def test_build_intro_messages_omits_world_foundations_when_no_presets():
    # All Layer 2 fields None → no WORLD FOUNDATIONS block.
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        genre="fantasy",
        tone="grimdark",
    )
    messages = _build_intro_messages(intro)
    user = messages[1]["content"]
    assert "WORLD FOUNDATIONS" not in user
    # Layer 1 bullets still work normally.
    assert "CREATION CONTEXT" in user
    assert "Genre: fantasy" in user
    assert "Tone: grimdark" in user


def test_creation_context_lines_omits_genre_when_genre_prompt_set():
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        genre="fantasy",
        genre_prompt="A dark fantasy setting.",
    )
    lines = _creation_context_lines(intro)
    assert not any(line.startswith("Genre:") for line in lines)


def test_creation_context_lines_omits_region_when_region_prompt_set():
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        starting_region="The Breach",
        region_prompt="The Breach is a wound in the land.",
    )
    lines = _creation_context_lines(intro)
    assert not any(line.startswith("Starting region:") for line in lines)


def test_creation_context_lines_omits_persona_when_persona_prompt_set():
    # Even with persona_name + persona_description set, the bare label
    # line is suppressed when persona_prompt is present — the WORLD
    # FOUNDATIONS paragraph carries the voice definition instead.
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        persona_id="oracle",
        persona_name="Oracle",
        persona_description="Prophetic and detached.",
        persona_prompt="The Oracle speaks in fragments of futures half-seen.",
    )
    lines = _creation_context_lines(intro)
    assert not any(line.startswith("DM persona:") for line in lines)


def test_creation_context_lines_omits_mood_when_mood_prompt_set():
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        mood="ominous",
        mood_prompt="Ominous stillness. Every silence means something is watching.",
    )
    lines = _creation_context_lines(intro)
    assert not any(line.startswith("DM mood:") for line in lines)


def test_creation_context_lines_keeps_tone_sandbox_permadeath_always():
    # These three have no preset counterpart — they should always land
    # as bare bullets when set, even when every other field has a
    # *_prompt set (which would otherwise empty the creation block).
    intro = IntroInput(
        world_name="W",
        player_name="P",
        player_class="C",
        tone="grimdark",
        sandbox=True,
        permadeath=True,
        genre="fantasy",
        genre_prompt="A dark fantasy setting.",
    )
    lines = _creation_context_lines(intro)
    assert any(line == "Tone: grimdark" for line in lines)
    assert any("Sandbox mode" in line for line in lines)
    assert any("Permadeath mode" in line for line in lines)
    assert not any(line.startswith("Genre:") for line in lines)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
