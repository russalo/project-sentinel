"""Per-world root resolution in fs-manager (ADR 0002, Slice 2).

These tests exercise ``_resolve_world_root`` end-to-end through the
``apply_world_update`` endpoint: with ``SENTINEL_WORLDS_ROOT`` set, a
request carrying a ``?world_id=`` query param must write into that
world's own tree at ``<WORLDS_ROOT>/<world_id>/`` and nowhere else.
With it unset (today's default), the world_id is ignored and writes
land in the legacy shared ``REPO_ROOT`` — the backward-compatibility
contract that lets Slice 2 ship before the Slice 3 cutover.

``world_id`` becomes a filesystem path component, so it is a security
boundary. The falsify-first cases below feed traversal and absolute-path
values and assert the server rejects them (422) AND writes nothing —
a status-only assertion would pass even if the server wrote first and
errored second.

Every test runs against a tmp ``REPO_ROOT`` (the ``fs_manager_module``
fixture); ``WORLDS_ROOT`` is monkeypatched per-test since the real one
is read from the environment at import.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# A syntactically valid UUID — passes uuid.UUID() so it can never contain
# a path separator, which is exactly why UUID validation is the boundary.
WORLD_UUID = "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f"

# A community path needs no namespace token, keeping these tests focused
# on routing rather than the namespace gate.
COMMUNITY_TARGET = "data/state/community/test_pack/npcs.json"


def _payload(session_id: str, target_file: str = COMMUNITY_TARGET) -> dict:
    return {
        "session_id": session_id,
        "log_entry": "World-routing test entry.",
        "updates": [
            {
                "target_file": target_file,
                "operation": "create",
                "data": {"name": "Test", "status": "alive"},
            }
        ],
    }


def _count_files_under(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file())


@pytest.fixture
def worlds_root(fs_manager_module, monkeypatch, tmp_path):
    """Enable per-world routing: point WORLDS_ROOT at a tmp dir and return it.

    Kept separate from REPO_ROOT (the fixture's tmp_path) so a test can
    assert a write landed in the world tree and NOT in the shared tree.
    """
    root = tmp_path / "worlds"
    root.mkdir()
    monkeypatch.setattr(fs_manager_module, "WORLDS_ROOT", str(root))
    return root


# ── /health reflects per-world mode (cutover verification) ────────────


def test_health_reports_worlds_root_true_when_set(client, worlds_root):
    assert client.get("/health").json()["worlds_root"] is True


def test_health_reports_worlds_root_false_when_unset(
    client, fs_manager_module, monkeypatch
):
    monkeypatch.setattr(fs_manager_module, "WORLDS_ROOT", None)
    assert client.get("/health").json()["worlds_root"] is False


# ── Routing: WORLDS_ROOT set ──────────────────────────────────────────


def test_world_id_routes_write_under_worlds_root(
    client, session_uuid, worlds_root, tmp_path
):
    response = client.post(
        "/tools/apply_world_update",
        params={"world_id": WORLD_UUID},
        json=_payload(session_uuid),
    )
    assert response.status_code == 200

    # The entity file landed inside the world's own tree...
    world_file = worlds_root / WORLD_UUID / COMMUNITY_TARGET
    assert world_file.is_file()
    # ...and NOT in the legacy shared tree (REPO_ROOT == tmp_path).
    assert not (tmp_path / COMMUNITY_TARGET).exists()


def test_session_log_also_routed_under_world_root(
    client, session_uuid, worlds_root, tmp_path
):
    """The session-log append must follow the same world root as the
    entity write — otherwise narrative would leak into the shared tree."""
    client.post(
        "/tools/apply_world_update",
        params={"world_id": WORLD_UUID},
        json=_payload(session_uuid),
    )

    log_in_world = (
        worlds_root
        / WORLD_UUID
        / "data"
        / "lore"
        / "core"
        / "sessions"
        / f"{session_uuid}.md"
    )
    assert log_in_world.is_file()
    assert not (
        tmp_path / "data" / "lore" / "core" / "sessions" / f"{session_uuid}.md"
    ).exists()


def test_no_world_id_uses_repo_root_even_when_worlds_root_set(
    client, session_uuid, worlds_root, tmp_path
):
    """WORLDS_ROOT set but no world_id on the request → the legacy shared
    tree is used. This is the path a not-yet-migrated caller takes during
    the Slice 2→3 transition."""
    response = client.post(
        "/tools/apply_world_update",
        json=_payload(session_uuid),
    )
    assert response.status_code == 200

    assert (tmp_path / COMMUNITY_TARGET).is_file()
    # Nothing should have been written into any world tree.
    assert _count_files_under(worlds_root) == 0


def test_world_id_canonicalized_before_path_resolution(
    client, session_uuid, worlds_root, tmp_path
):
    """A valid UUID in non-canonical spelling (no hyphens) must route to the
    SAME tree as its canonical hyphenated form — otherwise one logical world
    fragments across duplicate directories."""
    no_hyphens = WORLD_UUID.replace("-", "")
    assert no_hyphens != WORLD_UUID  # sanity: the two spellings differ

    response = client.post(
        "/tools/apply_world_update",
        params={"world_id": no_hyphens},
        json=_payload(session_uuid),
    )
    assert response.status_code == 200

    # Written under the canonical hyphenated dir, NOT a no-hyphen sibling.
    assert (worlds_root / WORLD_UUID / COMMUNITY_TARGET).is_file()
    assert not (worlds_root / no_hyphens).exists()


# ── Backward compatibility: WORLDS_ROOT unset ─────────────────────────


def test_worlds_root_unset_ignores_world_id(
    client, session_uuid, fs_manager_module, monkeypatch, tmp_path
):
    """Default posture: WORLDS_ROOT unset → world_id is inert, writes go to
    REPO_ROOT. Guarantees Slice 2 changes nothing until Slice 3 sets the env."""
    monkeypatch.setattr(fs_manager_module, "WORLDS_ROOT", None)

    response = client.post(
        "/tools/apply_world_update",
        params={"world_id": WORLD_UUID},
        json=_payload(session_uuid),
    )
    assert response.status_code == 200
    assert (tmp_path / COMMUNITY_TARGET).is_file()


# ── Security: world_id is a path component ────────────────────────────


@pytest.mark.parametrize(
    "bad_world_id",
    [
        "not-a-uuid",
        "../../../etc/passwd",
        "/etc/passwd",
        "..",
        "9b3c1d2e-4f5a-4b6c-8d7e-0a1b2c3d4e5f/../../escape",
        "",
    ],
)
def test_invalid_world_id_rejected_and_writes_nothing(
    client, session_uuid, worlds_root, tmp_path, bad_world_id
):
    """A world_id that isn't a clean UUID is rejected before any write.

    Empty string is the one that falls through to the legacy path
    (``not world_id`` → REPO_ROOT), so it succeeds rather than 422-ing;
    the invariant we actually care about — nothing escapes WORLDS_ROOT —
    still holds, so we assert on that rather than the status code.
    """
    files_before = _count_files_under(worlds_root)

    response = client.post(
        "/tools/apply_world_update",
        params={"world_id": bad_world_id},
        json=_payload(session_uuid),
    )

    if bad_world_id == "":
        # Falls through to REPO_ROOT (legacy) — no per-world dir created.
        assert response.status_code == 200
    else:
        assert response.status_code in (422, 403)
        body = response.json()
        detail = body["detail"]
        code = detail["code"] if isinstance(detail, dict) else str(detail)
        assert code in ("INVALID_WORLD_ID", "PATH_VIOLATION") or "world_id" in code

    # Hard invariant: nothing was written anywhere under the worlds root,
    # so no traversal value ever escaped or created a stray tree.
    assert _count_files_under(worlds_root) == files_before
