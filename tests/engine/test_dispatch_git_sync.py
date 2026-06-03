"""Unit tests for engine.dispatch.git_sync.commit_snapshot.

All tests use `httpx.MockTransport` for the transport layer — no real
network, no fixture server, no respx/pytest-httpx dependency. The
production API accepts an optional `client` keyword argument for this
purpose (same pattern as engine.dispatch.fs_manager.apply_world_update).
"""

import httpx
import pytest

from engine import Config
from engine.dispatch.git_sync import (
    DispatchResult,
    commit_snapshot,
    init_world,
    teardown_world,
)

VALID_SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _config(url: str = "http://git-sync.test") -> Config:
    return Config(openai_api_key="test-key", git_sync_url=url)


def _client_returning(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="")


def test_success_returns_ok_with_commit_hash():
    """Happy path: git-sync returns 200 with committed status."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "status": "committed",
                "commit": "a1b2c3d4",
                "session_id": VALID_SESSION_ID,
                "turn_number": 5,
            },
        )

    config = _config("http://git-sync.test")
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=5,
        summary="The Shadowbeast falls to Thalia's arrow.",
        client=_client_returning(handler),
    )

    assert isinstance(result, DispatchResult)
    assert result.ok is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.body["status"] == "committed"
    assert result.body["commit"] == "a1b2c3d4"

    assert captured["method"] == "POST"
    assert captured["url"] == "http://git-sync.test/tools/commit_snapshot"

    import json

    sent_body = json.loads(captured["body"])
    assert sent_body["session_id"] == VALID_SESSION_ID
    assert sent_body["turn_number"] == 5
    assert sent_body["summary"].startswith("The Shadowbeast")
    # No world_id passed → key omitted (legacy single-world payload shape).
    assert "world_id" not in sent_body


def test_world_id_included_in_payload_when_supplied():
    """ADR 0002: a supplied world_id is threaded into the commit payload."""
    import json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "committed", "commit": "deadbeef"})

    world_id = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"
    result = commit_snapshot(
        _config(),
        session_id=VALID_SESSION_ID,
        turn_number=1,
        summary="x",
        world_id=world_id,
        client=_client_returning(handler),
    )
    assert result.ok is True
    assert json.loads(captured["body"])["world_id"] == world_id


def test_no_changes_response_still_counts_as_success():
    """git-sync returning 200 with {status: 'no_changes'} is a normal
    outcome — two consecutive calls with no intervening fs-manager
    writes produce this. Callers should see ok=True."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "no_changes", "message": "No changes to commit."},
        )

    config = _config()
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=0,
        summary="empty turn",
        client=_client_returning(handler),
    )

    assert result.ok is True
    assert result.status_code == 200
    assert result.body["status"] == "no_changes"


def test_missing_session_id_returns_422():
    """git-sync rejects a payload without session_id. Our dispatcher
    never sends an empty session_id (the param is required), but if
    the server returns 422 for any reason we surface it as ok=False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": {
                    "code": "MISSING_SESSION_ID",
                    "detail": "session_id is required.",
                }
            },
        )

    config = _config()
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,  # server rejects anyway in this test
        turn_number=0,
        summary="stub",
        client=_client_returning(handler),
    )

    assert result.ok is False
    assert result.status_code == 422
    assert (
        "MISSING_SESSION_ID" in result.error or "session_id is required" in result.error
    )


def test_git_error_returns_500():
    """A git failure on the server side (non-git repo, broken index,
    etc.) lands as HTTP 500 with a GIT_ERROR code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "detail": {
                    "code": "GIT_ERROR",
                    "detail": "Repository not found at REPO_ROOT.",
                }
            },
        )

    config = _config()
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=1,
        summary="git broken",
        client=_client_returning(handler),
    )

    assert result.ok is False
    assert result.status_code == 500
    assert "GIT_ERROR" in result.error or "Repository not found" in result.error


def test_network_error_returns_status_zero():
    """Connection failures land as ok=False with status_code=0 (not an exception)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    config = _config()
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=0,
        summary="unreachable",
        client=_client_returning(handler),
    )

    assert result.ok is False
    assert result.status_code == 0
    assert "network error" in result.error
    assert "connection refused" in result.error


def test_url_uses_config_git_sync_url():
    """The URL should be built from config.git_sync_url, not hard-coded."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"status": "committed", "commit": "abcd1234"})

    config = _config("https://sentinel.tailscale.net:8012")
    commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=0,
        summary="tailnet commit",
        client=_client_returning(handler),
    )

    assert (
        captured["url"] == "https://sentinel.tailscale.net:8012/tools/commit_snapshot"
    )


def test_trailing_slash_in_git_sync_url_is_normalized():
    """A trailing slash in config.git_sync_url must not produce
    //tools/commit_snapshot — same defense as the fs-manager dispatcher."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"status": "committed", "commit": "abcd1234"})

    config = _config("http://git-sync.test/")  # note trailing slash
    commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=0,
        summary="trailing slash",
        client=_client_returning(handler),
    )

    assert captured["url"] == "http://git-sync.test/tools/commit_snapshot"
    assert "//tools" not in captured["url"]


def test_summary_newlines_are_normalized_to_spaces():
    """Summaries passed from callers are typically the first N chars
    of DM narrative text, which usually contains newlines. Git puts
    the summary directly into the commit subject line, so embedded
    newlines break the git log convention (title line separated from
    body by a blank line). The dispatcher should collapse all
    whitespace runs to single spaces before sending to git-sync."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "committed", "commit": "abcd1234"})

    config = _config()
    commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=1,
        summary="The fire crackles.\n\nThalia nocks an arrow.\nRussalo casts shadow.\r\n",
        client=_client_returning(handler),
    )

    sent_summary = captured["body"]["summary"]
    assert "\n" not in sent_summary
    assert "\r" not in sent_summary
    assert "\t" not in sent_summary
    # Content preserved, whitespace runs collapsed to single spaces
    assert (
        sent_summary
        == "The fire crackles. Thalia nocks an arrow. Russalo casts shadow."
    )


def test_summary_tab_and_multiple_spaces_are_collapsed():
    """str.split() with no arg handles all whitespace types uniformly,
    so verify tabs and runs of spaces also collapse correctly."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "committed", "commit": "abcd1234"})

    config = _config()
    commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=1,
        summary="word1\tword2    word3\n\n\nword4",
        client=_client_returning(handler),
    )

    assert captured["body"]["summary"] == "word1 word2 word3 word4"


def test_non_json_response_wraps_raw_text():
    """Server returning non-JSON still produces a structured result."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, content=b"<html>502 Bad Gateway</html>")

    config = _config()
    result = commit_snapshot(
        config,
        session_id=VALID_SESSION_ID,
        turn_number=0,
        summary="bad gateway",
        client=_client_returning(handler),
    )

    assert result.ok is False
    assert result.status_code == 502
    assert "raw" in result.body
    assert "Bad Gateway" in result.body["raw"]


def test_init_world_posts_world_id_and_returns_ok():
    """init_world POSTs {world_id} to /tools/init_world and surfaces success."""
    import json

    captured = {}
    world_id = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "initialized", "world_id": world_id})

    result = init_world(
        _config("http://git-sync.test"),
        world_id=world_id,
        client=_client_returning(handler),
    )
    assert result.ok is True
    assert result.status_code == 200
    assert result.body["status"] == "initialized"
    assert captured["url"] == "http://git-sync.test/tools/init_world"
    assert captured["body"] == {"world_id": world_id}


def test_init_world_skipped_status_is_success():
    """Pre-cutover git-sync returns 200 {status: skipped}; that's ok=True."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "skipped"})

    result = init_world(_config(), world_id="x", client=_client_returning(handler))
    assert result.ok is True
    assert result.body["status"] == "skipped"


def test_init_world_server_error_returns_ok_false():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"detail": {"code": "GIT_ERROR", "detail": "boom"}}
        )

    result = init_world(_config(), world_id="x", client=_client_returning(handler))
    assert result.ok is False
    assert result.status_code == 500
    assert "GIT_ERROR" in result.error or "boom" in result.error


def test_init_world_network_error_returns_status_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    result = init_world(_config(), world_id="x", client=_client_returning(handler))
    assert result.ok is False
    assert result.status_code == 0
    assert "network error" in result.error


def test_teardown_world_posts_world_id_and_session_id():
    import json

    captured = {}
    world_id = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "removed", "world_id": world_id})

    result = teardown_world(
        _config("http://git-sync.test"),
        world_id=world_id,
        session_id=VALID_SESSION_ID,
        client=_client_returning(handler),
    )
    assert result.ok is True
    assert result.body["status"] == "removed"
    assert captured["url"] == "http://git-sync.test/tools/teardown_world"
    assert captured["body"] == {"world_id": world_id, "session_id": VALID_SESSION_ID}


def test_teardown_world_omits_session_id_when_none():
    import json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "removed"})

    teardown_world(_config(), world_id="w", client=_client_returning(handler))
    assert "session_id" not in captured["body"]


def test_teardown_world_not_found_is_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "not_found"})

    result = teardown_world(_config(), world_id="w", client=_client_returning(handler))
    assert result.ok is True
    assert result.body["status"] == "not_found"


def test_teardown_world_error_returns_ok_false():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": {"code": "GIT_ERROR"}})

    result = teardown_world(_config(), world_id="w", client=_client_returning(handler))
    assert result.ok is False
    assert result.status_code == 500


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
