"""Pytest fixtures shared across backend tests.

Provides:
- ``tmp_data_dir``: a freshly-created ``data/`` tree under a tmpdir
  with the canonical ADR 0001 directory layout
- ``test_settings``: backend Settings pointing at the tmp data dir
  with stub OpenAI and MCP URLs
- ``app``: a FastAPI instance built against ``test_settings``
- ``client``: a ``fastapi.testclient.TestClient`` wired to ``app``
- ``fake_openai``: a shared fake OpenAI client the DM agent tests
  set responses on
- ``fake_dispatch_log``: a list that captures every
  ``engine.apply_world_update`` call so tests can assert on
  dispatched payloads without running a real fs-manager

The ``fake_openai`` and ``fake_dispatch_log`` fixtures monkey-patch
engine module attributes (``engine.agents.dm.build_client`` and
``engine.dispatch.fs_manager.apply_world_update``) so every
``engine.*`` call in the backend hits the stubs.
"""

from pathlib import Path
from typing import Any

import pytest

# These imports depend on the backend being importable — the sys.path
# manipulation happens via the repo-root pytest invocation (rootdir is
# set in pyproject or defaults to the cwd).


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    (data / "state" / "core" / "entities").mkdir(parents=True)
    (data / "state" / "core" / "locations").mkdir(parents=True)
    (data / "state" / "core" / "factions").mkdir(parents=True)
    (data / "state" / "core" / "items").mkdir(parents=True)
    (data / "state" / "core" / "world").mkdir(parents=True)
    (data / "state" / "core" / "sessions").mkdir(parents=True)
    (data / "lore" / "core" / "sessions").mkdir(parents=True)
    return data


@pytest.fixture
def test_settings(tmp_data_dir: Path):
    from backend.config import Settings

    return Settings(
        openai_api_key="test-key",
        openai_base_url=None,
        dm_model="test-model",
        max_completion_tokens=1234,
        fs_manager_url="http://fs-manager.test",
        git_sync_url="http://git-sync.test",
        data_dir=tmp_data_dir,
        worlds_root=None,
        cors_allowed_origins=("*",),
        cors_allow_all_origins=True,
        debug=True,
    )


@pytest.fixture
def app(
    test_settings,
    fake_openai,
    fake_dispatch_log,
    fake_commit_log,
    fake_teardown_log,
    monkeypatch,
):
    """Build a FastAPI app that uses the injected settings + fakes.

    Also monkey-patches the engine's dm.build_client and the
    dispatcher.apply_world_update at their public import sites inside
    the backend, so route handlers hit the stubs.
    """
    from fastapi import FastAPI

    from backend.routes import admin, feedback, health, session, stream, training, world

    import engine
    import engine.agents.dm as dm_module
    import engine.dispatch.fs_manager as dispatcher_module
    import engine.dispatch.git_sync as git_sync_module

    # Force every build_client call inside engine.agents.dm (run_turn,
    # stream_turn, generate_intro) to return our fake.
    monkeypatch.setattr(dm_module, "build_client", lambda config: fake_openai)

    # Capture dispatch calls without hitting any real server. Return
    # a happy DispatchResult so handlers proceed normally.
    def fake_dispatch(config, payload, *, world_id=None, client=None, timeout=30.0):
        fake_dispatch_log.append(
            {"config": config, "payload": payload, "world_id": world_id}
        )
        return engine.DispatchResult(ok=True, status_code=200, body={"success": True})

    monkeypatch.setattr(dispatcher_module, "apply_world_update", fake_dispatch)
    monkeypatch.setattr(engine, "apply_world_update", fake_dispatch)

    # Capture commit_snapshot calls the same way. Separate log so
    # tests can assert on the git-sync dispatches independently of
    # fs-manager dispatches.
    def fake_commit_snapshot(
        config,
        *,
        session_id,
        turn_number,
        summary,
        world_id=None,
        client=None,
        timeout=30.0,
    ):
        fake_commit_log.append(
            {
                "config": config,
                "session_id": session_id,
                "turn_number": turn_number,
                "summary": summary,
                "world_id": world_id,
            }
        )
        return engine.DispatchResult(
            ok=True,
            status_code=200,
            body={
                "status": "committed",
                "commit": "faceb00c",
                "session_id": session_id,
                "turn_number": turn_number,
            },
        )

    monkeypatch.setattr(git_sync_module, "commit_snapshot", fake_commit_snapshot)
    monkeypatch.setattr(engine, "commit_snapshot", fake_commit_snapshot)

    # Stub teardown_world (Slice 5) — capture + report removed, no real git-sync.
    def fake_teardown_world(
        config, *, world_id, session_id=None, client=None, timeout=30.0
    ):
        fake_teardown_log.append({"world_id": world_id, "session_id": session_id})
        return engine.DispatchResult(
            ok=True, status_code=200, body={"status": "removed", "world_id": world_id}
        )

    monkeypatch.setattr(git_sync_module, "teardown_world", fake_teardown_world)
    monkeypatch.setattr(engine, "teardown_world", fake_teardown_world)

    # Build the app with the test settings already loaded.
    from backend.admin_metrics import AdminMetrics
    from backend.concurrency import StreamSlotLimiter
    from backend.ratelimit import RateLimiter

    app = FastAPI()
    app.state.settings = test_settings
    # Mirror create_app: route handlers read request.app.state.rate_limiter.
    # Limits default to 0 (disabled) in test_settings, so it never throttles
    # unless a test overrides the settings.
    app.state.rate_limiter = RateLimiter()
    # Mirror create_app for the stream-slot limiter (ADR 0003 access dim #3).
    # test_settings.max_concurrent_streams defaults to 0 → disabled, so this
    # never rejects unless a test bumps the setting.
    app.state.stream_limiter = StreamSlotLimiter(test_settings.max_concurrent_streams)
    # Mirror create_app for the admin status dashboard counters.
    app.state.admin_metrics = AdminMetrics()
    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(stream.router)
    app.include_router(training.router)
    app.include_router(world.router)
    app.include_router(admin.router)
    app.include_router(feedback.router)
    return app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


# ── Fake OpenAI ──────────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeDelta:
    def __init__(self, content: str | None):
        self.content = content


class _FakeStreamChoice:
    def __init__(self, content: str | None):
        self.delta = _FakeDelta(content)


class _FakeStreamChunk:
    def __init__(self, content: str | None):
        self.choices = [_FakeStreamChoice(content)]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._blocking_response: str = ""
        self._stream_tokens: list[str | None] = []

    def set_blocking_response(self, content: str) -> None:
        self._blocking_response = content

    def set_stream_tokens(self, tokens: list[str | None]) -> None:
        self._stream_tokens = tokens

    def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(_FakeStreamChunk(tok) for tok in self._stream_tokens)
        return _FakeResponse(self._blocking_response)


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAI:
    def __init__(self) -> None:
        self.chat = _FakeChat()


@pytest.fixture
def fake_openai():
    return _FakeOpenAI()


@pytest.fixture
def fake_dispatch_log() -> list:
    return []


@pytest.fixture
def fake_commit_log() -> list:
    return []


@pytest.fixture
def fake_teardown_log() -> list:
    return []
