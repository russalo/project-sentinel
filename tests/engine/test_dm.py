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

from dataclasses import dataclass, field
from typing import Any, Iterable

import pytest

from engine.agents import dm as dm_agent
from engine.agents.dm import _build_messages, _strip_world_update, run_turn, stream_turn
from engine.prompts.dm import DM_SYSTEM_PROMPT
from engine.types import Config, DMTurnInput, DMTurnResult, WorldContext


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
                _FakeStreamChunk(choices=[_FakeStreamChoice(delta=_FakeDelta(content=token))])
                for token in self._stream_tokens
            )
        return _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=self._response_text))])


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def _make_config() -> Config:
    return Config(openai_api_key="test-key", dm_model="test-model", max_completion_tokens=1234)


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
            {"playerAction": "Enter the plaza.", "narrative": "Rain patters on cobblestone."},
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

    accumulated = "".join(stream_turn(_make_config(), _make_turn_input(), client=client))
    result = extract(
        accumulated,
        "123e4567-e89b-12d3-a456-426614174000",
        turn_number=1,
    )
    assert result.payload is not None
    assert result.payload["updates"][0]["target_file"] == "data/state/core/world/state.json"
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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
