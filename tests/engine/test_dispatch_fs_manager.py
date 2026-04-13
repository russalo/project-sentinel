"""Unit tests for engine.dispatch.fs_manager.apply_world_update.

All tests use `httpx.MockTransport` for the transport layer — no real
network, no fixture server, no respx/pytest-httpx dependency. The
production API accepts an optional `client` keyword argument for this
purpose.
"""

import httpx
import pytest

from engine import Config
from engine.dispatch.fs_manager import DispatchResult, apply_world_update


def _config(url: str = "http://fs-manager.test") -> Config:
    return Config(openai_api_key="test-key", fs_manager_url=url)


def _client_returning(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="")


def test_success_returns_ok_result():
    """Happy path: fs-manager returns 200 with a success body."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "success": True,
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "results": [{"status": "updated", "path": "data/state/core/entities/kael.json"}],
            },
        )

    config = _config("http://fs-manager.test")
    result = apply_world_update(
        config,
        {"session_id": "abc", "log_entry": "stub", "updates": [{"stub": True}]},
        client=_client_returning(handler),
    )

    assert isinstance(result, DispatchResult)
    assert result.ok is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.body["success"] is True
    assert "results" in result.body

    assert captured["method"] == "POST"
    assert captured["url"] == "http://fs-manager.test/tools/apply_world_update"


def test_schema_violation_returns_422():
    """fs-manager rejects an invalid payload with HTTP 422."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "detail": "'not-a-uuid' is not a 'uuid'",
                    "path": ["session_id"],
                }
            },
        )

    config = _config()
    result = apply_world_update(
        config,
        {"session_id": "not-a-uuid"},
        client=_client_returning(handler),
    )

    assert result.ok is False
    assert result.status_code == 422
    assert "VALIDATION_ERROR" in result.error or "not a 'uuid'" in result.error
    assert "detail" in result.body


def test_protected_field_violation_returns_403():
    """fs-manager rejects an attempt to modify a protected field with HTTP 403."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "detail": {
                    "code": "PROTECTED_FIELD_VIOLATION",
                    "detail": "Attempted to modify protected field(s): ['unique_id']",
                }
            },
        )

    config = _config()
    result = apply_world_update(config, {"updates": []}, client=_client_returning(handler))

    assert result.ok is False
    assert result.status_code == 403
    assert "PROTECTED_FIELD_VIOLATION" in result.error or "unique_id" in result.error


def test_network_error_returns_status_zero():
    """Connection failures land as ok=False with status_code=0 (not an exception)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    config = _config()
    result = apply_world_update(config, {}, client=_client_returning(handler))

    assert result.ok is False
    assert result.status_code == 0
    assert "network error" in result.error
    assert "connection refused" in result.error


def test_non_json_response_wraps_raw_text():
    """Server returning non-JSON still produces a structured result."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"<html>500 Internal Server Error</html>")

    config = _config()
    result = apply_world_update(config, {}, client=_client_returning(handler))

    assert result.ok is False
    assert result.status_code == 500
    assert "raw" in result.body
    assert "Internal Server Error" in result.body["raw"]


def test_url_uses_config_fs_manager_url():
    """The URL should be built from config.fs_manager_url, not hard-coded."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"success": True})

    config = _config("https://sentinel.tailscale.net:8010")
    apply_world_update(config, {}, client=_client_returning(handler))

    assert captured["url"] == "https://sentinel.tailscale.net:8010/tools/apply_world_update"


def test_accepts_list_body_gracefully():
    """A server response that is a JSON list (not dict) shouldn't crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "list"])

    config = _config()
    result = apply_world_update(config, {}, client=_client_returning(handler))

    assert result.ok is True
    assert result.body == {"raw": ["unexpected", "list"]}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
