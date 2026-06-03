"""Resolve the on-disk ``data/`` root for a world (ADR 0002 Slice 3).

The backend reads canonical state from a ``data/`` tree. With per-world
isolation, each world has its own tree at
``<SENTINEL_WORLDS_ROOT>/<world_id>/data``. When the env var is unset (the
default), the backend reads the single shared tree at ``settings.data_dir``
exactly as before — so this is backward-compatible until the operator flips
the cutover by setting ``SENTINEL_WORLDS_ROOT`` (the same var the MCP servers
already read).

This mirrors ``_resolve_world_root`` in the MCP servers
(``mcp-servers/{fs-manager,git-sync}/server.py``): ``world_id`` becomes a
filesystem path component, so it is a hard security boundary —

- UUID-validated, which rejects ``..``/``/``/control characters;
- canonicalized to the standard hyphenated lowercase spelling, so a
  non-hyphenated and a hyphenated form of the same UUID don't fragment into
  two trees;
- the resolved path is asserted to stay *directly* under the worlds root.

Raises ``ValueError`` (not an HTTP error) on a bad ``world_id`` so this stays
framework-agnostic; route handlers translate it (typically to "not found" /
400), and the headless export script can catch it too.
"""

import json
import uuid
from pathlib import Path


def resolve_world_data_dir(
    worlds_root: str | None,
    world_id: str | None,
    *,
    default_data_dir: Path,
) -> Path:
    """Return the ``data/`` directory the backend should read for this world.

    With ``worlds_root`` set AND a ``world_id`` given, returns
    ``<worlds_root>/<canonical world_id>/data``. Otherwise returns
    ``default_data_dir`` — the legacy single shared tree (also the path when no
    ``world_id`` is supplied, e.g. a session created before the cutover).
    """
    if not worlds_root or not world_id:
        return default_data_dir
    try:
        canonical_world_id = str(uuid.UUID(world_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"world_id is not a valid UUID: {world_id!r}") from exc
    base = Path(worlds_root).resolve()
    world_root = (base / canonical_world_id).resolve()
    if world_root.parent != base:
        raise ValueError(
            f"resolved world root {world_root!s} escapes worlds root {base!s}"
        )
    return world_root / "data"


_SESSIONS_REL = Path("state/core/sessions")


def iter_session_data_dirs(
    worlds_root: str | None,
    *,
    default_data_dir: Path,
) -> list[Path]:
    """Every ``data/`` dir whose sessions the dataset endpoints should scan.

    With ``worlds_root`` unset → just ``[default_data_dir]`` (the shared tree).
    With it set → one ``<world>/data`` per provisioned world directory, so the
    training browser keeps listing every world's sessions after the cutover.
    Returns an empty list if the worlds root doesn't exist yet (no worlds
    provisioned).
    """
    if not worlds_root:
        return [default_data_dir]
    base = Path(worlds_root)
    if not base.is_dir():
        return []
    try:
        children = sorted(base.iterdir())
    except OSError:
        # Removed/permission-changed mid-scan — degrade to "no worlds" rather
        # than crashing the listing/lookup endpoints.
        return []
    return [child / "data" for child in children if child.is_dir()]


def find_session_data_dir(
    worlds_root: str | None,
    session_id: str,
    *,
    default_data_dir: Path,
) -> Path | None:
    """Locate the ``data/`` dir that holds ``<session_id>.json``, or None.

    Unset ``worlds_root`` → always ``default_data_dir`` (the caller then reads
    it). Set → scan each world's sessions dir for the file and return that
    world's ``data/`` dir. ``session_id`` is UUID-validated first, since it is
    joined into a filesystem path.
    """
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError, TypeError):
        return None
    if not worlds_root:
        return default_data_dir
    for data_dir in iter_session_data_dirs(
        worlds_root, default_data_dir=default_data_dir
    ):
        if (data_dir / _SESSIONS_REL / f"{session_id}.json").is_file():
            return data_dir
    # Graceful migration: a session created before the cutover still lives in
    # the shared tree (its world_id is empty, so its writes also go there).
    # Fall back to it so pre-cutover sessions keep working after
    # SENTINEL_WORLDS_ROOT is set, instead of 404-ing. New per-world sessions
    # are found in their own tree by the loop above, so this never shadows them.
    if (default_data_dir / _SESSIONS_REL / f"{session_id}.json").is_file():
        return default_data_dir
    return None


def find_world_session(
    worlds_root: str | None,
    world_id: str,
    *,
    default_data_dir: Path,
) -> tuple[Path, str] | None:
    """Locate a world's current session for hydration (ADR 0002 Slice 4).

    Returns ``(data_dir, session_id)`` for the world's most-recent session, or
    ``None`` if the world has none (or ``world_id`` is malformed). The caller
    then ``read_session(data_dir, session_id)``.

    In per-world mode (``worlds_root`` set) the world's own tree holds only that
    world's sessions, so every session file qualifies. In legacy/shared mode the
    one tree holds many worlds' sessions, so we filter by the stored
    ``world_id`` field. ``world_id`` is UUID-validated (via
    ``resolve_world_data_dir``) before any path is built.
    """
    try:
        data_dir = resolve_world_data_dir(
            worlds_root, world_id, default_data_dir=default_data_dir
        )
    except ValueError:
        return None
    sessions_dir = data_dir / _SESSIONS_REL
    if not sessions_dir.is_dir():
        return None
    try:
        paths = list(sessions_dir.glob("*.json"))
    except OSError:
        # Dir removed / permissions changed mid-scan → "no session" rather
        # than a 500 on the resume path.
        return None
    candidates = []
    for path in paths:
        if not worlds_root:
            # Shared tree → many worlds; keep only this world's sessions.
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(raw, dict) or raw.get("world_id") != world_id:
                continue
        candidates.append(path)
    if not candidates:
        return None

    latest = max(candidates, key=_safe_mtime)
    return data_dir, latest.stem


def _safe_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def iter_worlds(
    worlds_root: str | None,
    *,
    default_data_dir: Path,
) -> list[tuple[str, Path, str]]:
    """Discover all worlds for the "my worlds" picker (ADR 0002 Slice 5).

    Returns ``(world_id, data_dir, session_id)`` for each world's most-recent
    session, ordered most-recently-played first (by session-file mtime). The
    caller ``read_session(data_dir, session_id)`` for display metadata.

    In per-world mode (``worlds_root`` set) each child dir under the worlds root
    is one world; its dir name is the ``world_id`` and must be a canonical UUID
    (``init_world`` provisions it that way). In legacy/shared mode the one tree
    holds many worlds' sessions, so group by the session's stored ``world_id``
    and keep the latest per world. **The emitted ``world_id`` is always a
    validated, canonical UUID** so the picker's ``/w/<world_id>`` link always
    round-trips through ``GET /api/world/<world_id>``; non-UUID dirs / stored
    ids and worlds with no session are skipped.
    """
    found: list[tuple[str, Path, str, float]] = []  # + mtime for ordering

    def _canonical_uuid(value: str) -> str | None:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError):
            return None

    if worlds_root:
        base = Path(worlds_root)
        if not base.is_dir():
            return []
        try:
            children = sorted(base.iterdir())
        except OSError:
            return []
        for child in children:
            if not child.is_dir():
                continue
            # The dir name must be a canonical UUID. A non-canonical name (a
            # stray/manually-created dir) can't be resolved by
            # find_world_session anyway (it builds the canonical path), so skip
            # it rather than surface a /w/<name> link that won't round-trip.
            world_id = _canonical_uuid(child.name)
            if world_id is None or world_id != child.name:
                continue
            session = find_world_session(
                worlds_root, world_id, default_data_dir=default_data_dir
            )
            if session is None:
                continue
            data_dir, session_id = session
            mtime = _safe_mtime(data_dir / _SESSIONS_REL / f"{session_id}.json")
            found.append((world_id, data_dir, session_id, mtime))
    else:
        sessions_dir = default_data_dir / _SESSIONS_REL
        if not sessions_dir.is_dir():
            return []
        # Group shared-tree sessions by stored world_id, keeping the latest.
        latest_by_world: dict[str, tuple[str, float]] = {}
        try:
            paths = list(sessions_dir.glob("*.json"))
        except OSError:
            return []
        for path in paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(raw, dict):
                continue
            # Validate the stored world_id is a UUID (skip non-UUID), but emit
            # it VERBATIM — find_world_session (legacy mode) matches sessions by
            # an exact `raw["world_id"] == world_id` compare, so canonicalizing
            # here would emit a /w/<id> link that no longer matches its own
            # stored spelling and 404s on resume. (Our minting is already
            # canonical; this only matters for hand-edited/imported ids.)
            stored = raw.get("world_id")
            if not stored or _canonical_uuid(stored) is None:
                continue
            world_id = stored
            mtime = _safe_mtime(path)
            prev = latest_by_world.get(world_id)
            if prev is None or mtime > prev[1]:
                latest_by_world[world_id] = (path.stem, mtime)
        for world_id, (session_id, mtime) in latest_by_world.items():
            found.append((world_id, default_data_dir, session_id, mtime))

    found.sort(key=lambda t: t[3], reverse=True)
    return [(w, d, s) for (w, d, s, _m) in found]
