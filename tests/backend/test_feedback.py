"""POST /api/feedback — submission validation, atomic write, and rate-limit."""

from __future__ import annotations

import dataclasses
import json

import pytest


@pytest.fixture
def feedback_settings(test_settings, tmp_path):
    """test_settings with feedback enabled at a tmp path + a generous rate cap.
    Settings is a frozen dataclass, so we use ``dataclasses.replace`` to
    produce a new instance rather than mutating in place."""
    return dataclasses.replace(
        test_settings,
        feedback_root=tmp_path / "feedback",
        rl_feedback_per_hour=100,
    )


@pytest.fixture
def feedback_client(client, feedback_settings):
    """A TestClient wired with feedback enabled. `client` already exposes the
    full FastAPI app under test; swap settings the route reads via app.state."""
    client.app.state.settings = feedback_settings
    return client


def _valid_payload(**overrides):
    """A minimal valid POST body. Tests override one field at a time."""
    base = {
        "subject": "Pills overlap text on iOS",
        "body": "When I tap a pill, the text behind it shows through.",
        "category": "ui-ux",
        "platform": "iOS",
        "browser": "Chrome",
    }
    base.update(overrides)
    return base


# ── 503 when feedback disabled ─────────────────────────────────────────


def test_returns_503_when_feedback_root_unset(client, test_settings):
    # test_settings defaults feedback_root=None; the route should refuse.
    client.app.state.settings = dataclasses.replace(test_settings, feedback_root=None)
    resp = client.post("/api/feedback", json=_valid_payload())
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "FEEDBACK_DISABLED"


# ── happy path ─────────────────────────────────────────────────────────


def test_accepts_minimal_valid_payload(feedback_client, feedback_settings):
    resp = feedback_client.post("/api/feedback", json=_valid_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "id" in body
    # File landed on disk
    written = list(feedback_settings.feedback_root.rglob("*.json"))
    assert len(written) == 1, written
    record = json.loads(written[0].read_text(encoding="utf-8"))
    assert record["subject"] == "Pills overlap text on iOS"
    assert record["category"] == "ui-ux"
    assert "submittedAt" in record
    assert "userAgent" in record
    assert "clientIp" in record


def test_accepts_all_optional_fields(feedback_client, feedback_settings):
    resp = feedback_client.post(
        "/api/feedback",
        json=_valid_payload(
            severity="high",
            reproducible="sometimes",
            handle="tester-alpha",
            worldId="fa0ec595-37b5-41b0-a4ff-3f8d176a0047",
            sessionId="4f1cebed-4bda-46eb-824c-7ccb34671278",
            viewport="375x812",
            currentUrl="https://sentinel.russalo.com/alpha/w/fa0ec595-37b5-41b0-a4ff-3f8d176a0047",
            bundleHash="BtGeQSxG",
        ),
    )
    assert resp.status_code == 200, resp.text
    written = list(feedback_settings.feedback_root.rglob("*.json"))
    record = json.loads(written[0].read_text(encoding="utf-8"))
    assert record["severity"] == "high"
    assert record["worldId"] == "fa0ec595-37b5-41b0-a4ff-3f8d176a0047"
    assert record["bundleHash"] == "BtGeQSxG"


def test_writes_into_dated_subdirectory(feedback_client, feedback_settings):
    feedback_client.post("/api/feedback", json=_valid_payload())
    # Expect <root>/YYYY-MM-DD/<ts>-<id>.json — one date dir, one JSON file
    subdirs = list(feedback_settings.feedback_root.iterdir())
    assert len(subdirs) == 1
    assert subdirs[0].is_dir()
    assert len(subdirs[0].name) == 10  # YYYY-MM-DD
    files = list(subdirs[0].iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".json"
    # No leftover .json.tmp atomic-write file
    tmps = list(subdirs[0].glob("*.json.tmp"))
    assert tmps == []


def test_userAgent_captured_from_request_header_not_body(
    feedback_client,
    feedback_settings,
):
    # The SPA can't be trusted to pass the user-agent correctly via the body
    # (and it's redundant — the request header already has it). Verify the
    # server reads it from the header even when the body would have something
    # else.
    resp = feedback_client.post(
        "/api/feedback",
        json=_valid_payload(),
        headers={"user-agent": "Mozilla/5.0 (iPhone test) AppleWebKit"},
    )
    assert resp.status_code == 200
    written = list(feedback_settings.feedback_root.rglob("*.json"))
    record = json.loads(written[0].read_text(encoding="utf-8"))
    assert "iPhone test" in record["userAgent"]


# ── validation ─────────────────────────────────────────────────────────


def test_rejects_empty_subject(feedback_client):
    resp = feedback_client.post("/api/feedback", json=_valid_payload(subject=""))
    assert resp.status_code == 422


def test_rejects_oversized_subject(feedback_client):
    resp = feedback_client.post("/api/feedback", json=_valid_payload(subject="x" * 200))
    assert resp.status_code == 422


def test_rejects_empty_body(feedback_client):
    resp = feedback_client.post("/api/feedback", json=_valid_payload(body=""))
    assert resp.status_code == 422


def test_rejects_oversized_body(feedback_client):
    resp = feedback_client.post("/api/feedback", json=_valid_payload(body="x" * 5000))
    assert resp.status_code == 422


def test_rejects_invalid_category(feedback_client):
    resp = feedback_client.post(
        "/api/feedback", json=_valid_payload(category="nonsense")
    )
    assert resp.status_code == 422


def test_rejects_invalid_severity(feedback_client):
    resp = feedback_client.post(
        "/api/feedback", json=_valid_payload(severity="critical")
    )
    assert resp.status_code == 422


def test_rejects_invalid_reproducible(feedback_client):
    resp = feedback_client.post(
        "/api/feedback", json=_valid_payload(reproducible="maybe")
    )
    assert resp.status_code == 422


# ── rate limiting ──────────────────────────────────────────────────────


def test_rate_limit_fires_at_cap(feedback_client, feedback_settings):
    # Tighten the cap on a fresh Settings (frozen → replace)
    feedback_client.app.state.settings = dataclasses.replace(
        feedback_settings,
        rl_feedback_per_hour=2,
    )
    # Two submissions allowed
    r1 = feedback_client.post("/api/feedback", json=_valid_payload())
    r2 = feedback_client.post("/api/feedback", json=_valid_payload())
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Third should be rejected
    r3 = feedback_client.post("/api/feedback", json=_valid_payload())
    assert r3.status_code == 429
    assert r3.json()["detail"]["code"] == "RATE_LIMITED"
    assert r3.headers.get("Retry-After") == "3600"


def test_rate_limit_zero_means_unlimited(feedback_client, feedback_settings):
    feedback_client.app.state.settings = dataclasses.replace(
        feedback_settings,
        rl_feedback_per_hour=0,
    )
    # Many submissions all succeed
    for _ in range(20):
        resp = feedback_client.post("/api/feedback", json=_valid_payload())
        assert resp.status_code == 200, resp.text
