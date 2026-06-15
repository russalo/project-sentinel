"""Tests for system messages (RFC 0002).

Covers:
- Storage helpers in ``backend/state/system_messages.py`` — roundtrips,
  filters, sort order.
- HTTP routes in ``backend/routes/system_messages.py`` — public GET,
  admin CRUD, validation, soft-delete semantics.

Auth is intentionally NOT tested here — the admin endpoints carry no
server-side gate. The Caddyfile-edge 404 of ``/api/admin/*`` is the
auth layer, and that's covered by ``tests/test_caddy_invariant.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.state import system_messages as sm_state


# ── Storage layer ──────────────────────────────────────────────────


def test_create_then_read_roundtrip(tmp_data_dir):
    msg = sm_state.create(
        tmp_data_dir,
        title="Hello cohort",
        body="The silhouette **flipped** today.",
    )
    loaded = sm_state.read(tmp_data_dir, msg.id)
    assert loaded is not None
    assert loaded.id == msg.id
    assert loaded.title == "Hello cohort"
    assert loaded.body == "The silhouette **flipped** today."
    assert loaded.category == "info"
    assert loaded.pinned is False
    assert loaded.expires_at is None
    assert loaded.deleted_at is None


def test_create_persists_to_per_message_json_file(tmp_data_dir):
    msg = sm_state.create(tmp_data_dir, title="t", body="b")
    expected_path = (
        tmp_data_dir / "state" / "core" / "system_messages" / f"{msg.id}.json"
    )
    assert expected_path.exists()
    raw = json.loads(expected_path.read_text())
    assert raw["id"] == msg.id
    assert raw["title"] == "t"


def test_create_rejects_unknown_category(tmp_data_dir):
    with pytest.raises(ValueError, match="category"):
        sm_state.create(tmp_data_dir, title="t", body="b", category="bogus")


def test_read_returns_none_for_non_uuid_id(tmp_data_dir):
    # Path-traversal defense — non-UUID IDs are simply not found, never
    # interpolated into a path that could escape the messages dir.
    assert sm_state.read(tmp_data_dir, "../etc/passwd") is None
    assert sm_state.read(tmp_data_dir, "not-a-uuid") is None


def test_read_returns_none_for_unknown_id(tmp_data_dir):
    assert sm_state.read(tmp_data_dir, "00000000-0000-0000-0000-000000000000") is None


def test_list_all_includes_deleted_and_expired(tmp_data_dir):
    """Admin-side listing surfaces everything on disk."""
    sm_state.create(tmp_data_dir, title="active", body="b")
    deleted = sm_state.create(tmp_data_dir, title="deleted", body="b")
    sm_state.soft_delete(tmp_data_dir, deleted.id)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    sm_state.create(tmp_data_dir, title="expired", body="b", expires_at=past)
    all_msgs = sm_state.list_all(tmp_data_dir)
    assert len(all_msgs) == 3


def test_list_active_filters_soft_deleted(tmp_data_dir):
    keep = sm_state.create(tmp_data_dir, title="keep", body="b")
    drop = sm_state.create(tmp_data_dir, title="drop", body="b")
    sm_state.soft_delete(tmp_data_dir, drop.id)
    active = sm_state.list_active(tmp_data_dir)
    assert [m.id for m in active] == [keep.id]


def test_list_active_filters_expired(tmp_data_dir):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    sm_state.create(tmp_data_dir, title="expired", body="b", expires_at=past)
    keep = sm_state.create(tmp_data_dir, title="future", body="b", expires_at=future)
    perm = sm_state.create(tmp_data_dir, title="no expiry", body="b")
    active = sm_state.list_active(tmp_data_dir)
    ids = {m.id for m in active}
    assert keep.id in ids
    assert perm.id in ids
    assert len(active) == 2


def test_list_active_handles_z_suffix_expiry(tmp_data_dir):
    """An ``expires_at`` ending in ``Z`` (a common ISO variant the AdminUI
    or a curl-wielding operator might produce) must still filter correctly.
    The old lexicographic compare failed this — ``.`` (46) < ``Z`` (90) so
    a fractional ``+00:00`` "now" appears less than a ``Z`` "then" and the
    message survives past expiry."""
    sm_state.create(
        tmp_data_dir, title="z-expired", body="b", expires_at="2000-01-01T00:00:00Z"
    )
    active = sm_state.list_active(tmp_data_dir)
    assert active == []


def test_list_active_handles_fractional_seconds_expiry(tmp_data_dir):
    """Fractional-second timestamps mustn't trip the parser. Server-side
    ``_now_iso`` produces ``+00:00`` suffix with microseconds; a fractional
    expires_at coming back from the API needs to compare correctly."""
    past_fractional = "2000-01-01T00:00:00.123456+00:00"
    future_fractional = (
        (datetime.now(timezone.utc) + timedelta(hours=1))
        .isoformat()
        .replace("+00:00", ".999999+00:00")
    )
    sm_state.create(tmp_data_dir, title="expired", body="b", expires_at=past_fractional)
    keep = sm_state.create(
        tmp_data_dir, title="future-frac", body="b", expires_at=future_fractional
    )
    active = sm_state.list_active(tmp_data_dir)
    assert [m.id for m in active] == [keep.id]


def test_list_active_keeps_malformed_expiry(tmp_data_dir):
    """Unparseable ``expires_at`` is treated as never-expiring so a typo
    can't silently hide an operator message. ``_is_expired`` returning
    False on parse failure is the documented escape hatch."""
    sm_state.create(tmp_data_dir, title="garbled", body="b", expires_at="not-a-date")
    active = sm_state.list_active(tmp_data_dir)
    assert len(active) == 1


def test_list_active_sorts_pinned_first_then_newest(tmp_data_dir):
    """Pinned messages come first regardless of published_at; within
    each group, newest first."""
    m1 = sm_state.create(tmp_data_dir, title="m1-oldest", body="b")
    m2 = sm_state.create(tmp_data_dir, title="m2-mid", body="b")
    m3_pinned = sm_state.create(
        tmp_data_dir, title="m3-pinned-oldest", body="b", pinned=True
    )
    m4 = sm_state.create(tmp_data_dir, title="m4-newest", body="b")
    m5_pinned = sm_state.create(
        tmp_data_dir, title="m5-pinned-newest", body="b", pinned=True
    )
    active = sm_state.list_active(tmp_data_dir)
    # Expected order: pinned newest first (m5, m3), then unpinned newest
    # first (m4, m2, m1).
    assert [m.id for m in active] == [m5_pinned.id, m3_pinned.id, m4.id, m2.id, m1.id]


def test_update_partial_keeps_unchanged_fields(tmp_data_dir):
    msg = sm_state.create(tmp_data_dir, title="orig", body="orig body", pinned=False)
    updated = sm_state.update(tmp_data_dir, msg.id, title="new title")
    assert updated is not None
    assert updated.title == "new title"
    assert updated.body == "orig body"  # untouched
    assert updated.pinned is False  # untouched


def test_update_can_clear_expires_at(tmp_data_dir):
    """The sentinel ``clear_expires_at=True`` is the only way to reset
    a previously-set expiry to None, since None-as-not-set is
    indistinguishable from None-as-cleared otherwise."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    msg = sm_state.create(tmp_data_dir, title="t", body="b", expires_at=future)
    assert msg.expires_at == future
    updated = sm_state.update(tmp_data_dir, msg.id, clear_expires_at=True)
    assert updated is not None
    assert updated.expires_at is None


def test_update_returns_none_for_unknown_id(tmp_data_dir):
    assert (
        sm_state.update(tmp_data_dir, "00000000-0000-0000-0000-000000000000", title="x")
        is None
    )


def test_update_rejects_unknown_category(tmp_data_dir):
    msg = sm_state.create(tmp_data_dir, title="t", body="b")
    with pytest.raises(ValueError, match="category"):
        sm_state.update(tmp_data_dir, msg.id, category="bogus")


def test_soft_delete_sets_deleted_at_and_hides_from_active(tmp_data_dir):
    msg = sm_state.create(tmp_data_dir, title="bye", body="b")
    deleted = sm_state.soft_delete(tmp_data_dir, msg.id)
    assert deleted is not None
    assert deleted.deleted_at is not None
    # Active feed no longer includes it
    assert msg.id not in {m.id for m in sm_state.list_active(tmp_data_dir)}
    # But list_all still does (audit-friendly)
    assert msg.id in {m.id for m in sm_state.list_all(tmp_data_dir)}


def test_soft_delete_returns_none_for_unknown(tmp_data_dir):
    assert (
        sm_state.soft_delete(tmp_data_dir, "00000000-0000-0000-0000-000000000000")
        is None
    )


# ── HTTP routes ─────────────────────────────────────────────────────


def test_get_messages_empty_initially(client):
    r = client.get("/api/system-messages")
    assert r.status_code == 200
    assert r.json() == {"messages": []}


def test_post_then_get_roundtrip(client):
    r = client.post(
        "/api/admin/system-messages",
        json={
            "title": "Maintenance",
            "body": "Down 5pm PDT",
            "category": "maintenance",
        },
    )
    assert r.status_code == 200
    created = r.json()
    assert created["title"] == "Maintenance"
    assert created["category"] == "maintenance"
    assert created["id"]
    assert created["published_at"]

    r2 = client.get("/api/system-messages")
    assert r2.status_code == 200
    msgs = r2.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["id"] == created["id"]


def test_post_validates_required_fields(client):
    # Empty title
    r = client.post("/api/admin/system-messages", json={"title": "", "body": "b"})
    assert r.status_code == 422
    # Empty body
    r = client.post("/api/admin/system-messages", json={"title": "t", "body": ""})
    assert r.status_code == 422


def test_post_validates_category(client):
    # ``category`` is typed as ``Literal[...]`` in the Pydantic request
    # model, so an unknown value fails schema validation at the route
    # boundary (422) — never reaching the state-layer ValueError → 400.
    r = client.post(
        "/api/admin/system-messages",
        json={"title": "t", "body": "b", "category": "bogus"},
    )
    assert r.status_code == 422


def test_patch_partial_update(client):
    r = client.post(
        "/api/admin/system-messages",
        json={"title": "orig", "body": "orig body"},
    )
    mid = r.json()["id"]
    r2 = client.patch(
        f"/api/admin/system-messages/{mid}",
        json={"title": "updated"},
    )
    assert r2.status_code == 200
    assert r2.json()["title"] == "updated"
    assert r2.json()["body"] == "orig body"


def test_patch_404_on_unknown(client):
    r = client.patch(
        "/api/admin/system-messages/00000000-0000-0000-0000-000000000000",
        json={"title": "x"},
    )
    assert r.status_code == 404


def test_delete_soft_deletes_and_filters_from_get(client):
    r = client.post("/api/admin/system-messages", json={"title": "bye", "body": "b"})
    mid = r.json()["id"]
    r2 = client.delete(f"/api/admin/system-messages/{mid}")
    assert r2.status_code == 200
    assert r2.json()["deleted_at"] is not None
    # The cohort-facing GET no longer surfaces it
    r3 = client.get("/api/system-messages")
    assert mid not in {m["id"] for m in r3.json()["messages"]}


def test_delete_404_on_unknown(client):
    r = client.delete("/api/admin/system-messages/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_admin_list_surfaces_deleted_and_expired(client):
    """Admin-side list (separate from the public feed) sees everything."""
    r1 = client.post(
        "/api/admin/system-messages", json={"title": "active", "body": "b"}
    )
    r2 = client.post(
        "/api/admin/system-messages", json={"title": "deleted", "body": "b"}
    )
    client.delete(f"/api/admin/system-messages/{r2.json()['id']}")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r3 = client.post(
        "/api/admin/system-messages",
        json={"title": "expired", "body": "b", "expires_at": past},
    )
    r = client.get("/api/admin/system-messages")
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["messages"]}
    assert {r1.json()["id"], r2.json()["id"], r3.json()["id"]} == ids


def test_get_feed_sorts_pinned_first_then_newest(client):
    """End-to-end through the HTTP layer: verify the sort order matches
    what the storage layer produces."""
    # Create a sequence so timestamps differ; pin some
    a = client.post(
        "/api/admin/system-messages", json={"title": "a-oldest", "body": "b"}
    ).json()
    b = client.post(
        "/api/admin/system-messages",
        json={"title": "b-mid-pinned", "body": "b", "pinned": True},
    ).json()
    c = client.post(
        "/api/admin/system-messages", json={"title": "c-newest", "body": "b"}
    ).json()

    r = client.get("/api/system-messages")
    msgs = r.json()["messages"]
    # Pinned 'b' is first; then unpinned newest-first: c, a
    assert [m["id"] for m in msgs] == [b["id"], c["id"], a["id"]]
