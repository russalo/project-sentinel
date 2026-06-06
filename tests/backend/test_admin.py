"""Operator status dashboard endpoint + counter behavior.

Two layers:

- ``AdminMetrics`` direct unit tests: thread-safe bumps, snapshot coherence,
  active-stream underflow defense.
- Route-level tests through the FastAPI TestClient: the JSON endpoint shape is
  the contract the dashboard polls; the HTML page is the operator UX.

The Caddy-edge exclusion (``/api/admin*`` and ``/_status`` returning 404 on
the public edge) is tested separately in ``tests/test_caddy_invariant.py``;
here we only verify the backend serves them on its loopback bind.
"""

from __future__ import annotations

import threading

from backend.admin_metrics import AdminMetrics


# ── AdminMetrics unit tests ────────────────────────────────────────────


def test_initial_snapshot_is_zeroed():
    m = AdminMetrics()
    s = m.snapshot()
    assert s["streams_served_total"] == 0
    assert s["capacity_rejected_total"] == 0
    assert s["rate_limited_total"] == 0
    assert s["active_streams"] == 0
    assert s["uptime_seconds"] >= 0


def test_stream_acquired_bumps_served_and_active():
    m = AdminMetrics()
    m.stream_acquired()
    m.stream_acquired()
    s = m.snapshot()
    assert s["streams_served_total"] == 2
    assert s["active_streams"] == 2


def test_stream_released_decrements_active_only():
    m = AdminMetrics()
    m.stream_acquired()
    m.stream_acquired()
    m.stream_released()
    s = m.snapshot()
    # Served is cumulative (NOT a gauge); active is the gauge.
    assert s["streams_served_total"] == 2
    assert s["active_streams"] == 1


def test_active_streams_does_not_underflow():
    """A misuse (release without acquire) clamps at 0, doesn't underflow."""
    m = AdminMetrics()
    m.stream_released()  # spurious release
    m.stream_released()  # another
    assert m.snapshot()["active_streams"] == 0


def test_capacity_and_rate_limit_counters_independent():
    m = AdminMetrics()
    m.capacity_rejected()
    m.capacity_rejected()
    m.capacity_rejected()
    m.rate_limited()
    s = m.snapshot()
    assert s["capacity_rejected_total"] == 3
    assert s["rate_limited_total"] == 1
    # Neither affects active or served counters
    assert s["active_streams"] == 0
    assert s["streams_served_total"] == 0


def test_thread_safe_under_concurrent_bumps():
    """100 threads each bumping streams_served 100×; expect 10,000 total.

    Verifies the lock is real — without it, the counter would lose increments
    on a non-atomic int += 1.
    """
    m = AdminMetrics()

    def bump():
        for _ in range(100):
            m.stream_acquired()

    threads = [threading.Thread(target=bump) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.snapshot()["streams_served_total"] == 10_000
    assert m.snapshot()["active_streams"] == 10_000


# ── Route-level: /api/admin/status shape ───────────────────────────────


def test_status_endpoint_shape(client):
    """The JSON contract the dashboard polls. Field additions are fine
    (the dashboard tolerates them); removals or renames break it."""
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    d = r.json()

    # Top-level keys
    assert "uptime_seconds" in d
    assert "concurrency" in d
    assert "throughput" in d
    assert "mcp" in d
    assert "settings_posture" in d

    # concurrency block
    assert "active" in d["concurrency"]
    assert "max" in d["concurrency"]
    assert "capacity_rejected_total" in d["concurrency"]
    assert d["concurrency"]["active"] == 0
    # test_settings.max_concurrent_streams defaults to 0 (disabled)
    assert d["concurrency"]["max"] == 0

    # throughput block
    assert d["throughput"]["streams_served_total"] == 0
    assert d["throughput"]["rate_limited_total"] == 0

    # settings_posture reflects the test settings
    sp = d["settings_posture"]
    assert sp["world_token_enforced"] is False
    assert sp["max_concurrent_streams"] == 0


def test_status_endpoint_reflects_counter_state(client):
    """A counter bump becomes visible on the next snapshot read."""
    metrics = client.app.state.admin_metrics
    metrics.stream_acquired()
    metrics.capacity_rejected()
    metrics.capacity_rejected()
    metrics.rate_limited()

    r = client.get("/api/admin/status")
    assert r.status_code == 200
    d = r.json()
    assert d["concurrency"]["active"] == 1
    assert d["concurrency"]["capacity_rejected_total"] == 2
    assert d["throughput"]["streams_served_total"] == 1
    assert d["throughput"]["rate_limited_total"] == 1


def test_status_endpoint_mcp_unreachable_does_not_500(client):
    """MCP servers may be down during dev — the endpoint must degrade gracefully.

    The test fixture doesn't run real MCP servers on :8010/:8012; this
    confirms the dashboard call returns 200 with an `unreachable` status
    instead of bubbling up the connection error as a 500.
    """
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    d = r.json()
    # Both are unreachable in the test fixture — status is non-"ok"
    # (and definitely not a Python traceback / exception payload)
    assert "status" in d["mcp"]["fs_manager"]
    assert "status" in d["mcp"]["git_sync"]
    # The string starts with "unreachable" or is "http <code>" — never raises
    assert isinstance(d["mcp"]["fs_manager"]["status"], str)
    assert isinstance(d["mcp"]["git_sync"]["status"], str)


def test_status_html_page_returns_polling_dashboard(client):
    """`/_status` returns an HTML page that polls `/api/admin/status`."""
    r = client.get("/_status")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    # Confirms the page polls the JSON endpoint
    assert "/api/admin/status" in body
    # Confirms the polling loop exists
    assert "setInterval" in body
    # Confirms it's a self-contained page (no external assets that wouldn't
    # work on a tailnet/loopback-only deploy)
    assert "<script" in body
    # No external script URLs (defends against drive-by drift adding a CDN)
    assert "src=" not in body or 'src="http' not in body


# ── Defense-in-depth (bot review on PR #107) ───────────────────────────


def test_mcp_health_handles_non_dict_json(client, monkeypatch):
    """gemini medium on PR #107: if an MCP server returns non-dict JSON (a
    list, string, null — well-formed-but-unexpected), the dashboard must
    treat it as "no fields" rather than crash with AttributeError on .get()."""
    import httpx

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return ["unexpected", "list", "shape"]

    def fake_get(url, timeout=None):
        return _FakeResp()

    monkeypatch.setattr(httpx, "get", fake_get)
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    d = r.json()
    # Both MCP entries should have the default fields populated, not a 500
    assert d["mcp"]["fs_manager"]["status"] == "ok"
    assert d["mcp"]["fs_manager"]["worlds_root"] is False


def test_mcp_health_uses_configured_urls(client, monkeypatch):
    """codex P2 on PR #107: a deploy with non-default FS_MANAGER_URL /
    GIT_SYNC_URL (e.g. a Docker service name) must have its actual URL hit,
    not hardcoded localhost. The dashboard would otherwise lie about
    actually-healthy MCP servers."""
    from dataclasses import replace
    import httpx

    client.app.state.settings = replace(
        client.app.state.settings,
        fs_manager_url="http://fs-manager.example:9999",
        git_sync_url="http://git-sync.example:9999",
    )

    seen_urls = []

    def fake_get(url, timeout=None):
        seen_urls.append(url)

        class _R:
            status_code = 200
            headers = {"content-type": "application/json"}

            def json(self):
                return {"status": "ok", "worlds_root": False}

        return _R()

    monkeypatch.setattr(httpx, "get", fake_get)
    r = client.get("/api/admin/status")
    assert r.status_code == 200
    # The configured URLs (with /health appended) must have been called —
    # NOT 127.0.0.1:8010/8012.
    assert "http://fs-manager.example:9999/health" in seen_urls
    assert "http://git-sync.example:9999/health" in seen_urls


def test_status_html_validates_response_shape():
    """gemini high on PR #107: the dashboard JS must validate the response
    shape before accessing nested properties, or a malformed payload would
    crash the polling loop with TypeError.

    We verify the source has the guard rather than running the JS — exact
    behavior is documented in the comment in admin.py.
    """
    from backend.routes import admin as admin_mod

    assert "typeof d !== 'object'" in admin_mod._STATUS_HTML, (
        "dashboard JS must defensively type-check the API response"
    )
    assert "malformed response" in admin_mod._STATUS_HTML, (
        "dashboard JS must surface the malformed-response case to the operator"
    )
