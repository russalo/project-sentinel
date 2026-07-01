"""Lorekeeper retrieval — the backend (IO) half of the RFC-0011 fold.

Calls ``poggio`` (an external, trellis-based lore-retrieval tool) as a
subprocess to retrieve canon relevant to the current turn, lean-projects the
hits, and returns them for the engine to render
(``engine.agents.lorekeeper.render_canon_block``). All IO lives here — the
engine stays pure per its boundary contract.

**Fail-open by contract:** any retrieval failure (poggio not on PATH, a
non-zero exit, a timeout, malformed JSON) is logged and degrades to ``[]``.
Retrieval is an *enhancement*; a missing or broken tool must never break a
turn. It also short-circuits to ``[]`` when disabled, so the dormant default
does no work.

See ADR-0006 (retrieval substrate) and RFC-0011 (this fold).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from engine.types import WorldContext

    from ..config import Settings

logger = logging.getLogger(__name__)

# Budget (RFC-0011): scene entities + a bm25 "have we established X?" on the
# action, deduped and capped. Tuned later with real telemetry.
_SCENE_LIMIT = 5
_ESTABLISHED_LIMIT = 3
_TOTAL_CAP = 8
_TIMEOUT_S = 10.0
# The schema-version probe is a trivial version print (no trellis, no
# retrieval), so it gets a much shorter timeout than a recipe query — it runs
# synchronously in the turn path, and a hung probe shouldn't delay a turn by
# the full retrieval budget (gemini-medium on PR #166).
_SCHEMA_TIMEOUT_S = 3.0

# RFC-0012: the poggio output-schema this fold is written against. poggio's
# `schema-version` probe must report exactly this, or retrieval is disabled for
# the process (deploy-safety — a wrong/old binary emits a different hit shape).
# Bump in lockstep with the pinned `poggio >= x` when adopting a new schema.
_EXPECTED_SCHEMA = "0.2"
# Process-level cache of the schema-version verdict, keyed by binary path. The
# binary can't change under a running process, so one probe per binary suffices.
_schema_ok_cache: dict[str, bool] = {}


def retrieve_canon(
    data_dir: Path,
    world_context: "WorldContext",
    player_action: str,
    settings: "Settings",
) -> list[dict[str, Any]]:
    """Retrieve + lean-project canon hits for this turn, or ``[]``.

    Dormant fast-path when disabled. ``poggio``'s ``--world`` wants the dir
    *containing* ``data/``, so we pass ``data_dir.parent`` (the world root in
    both shared and per-world modes).
    """
    if not settings.lorekeeper_enabled:
        return []
    # Deploy-safety (RFC-0012): a wrong/old/missing poggio emits a different hit
    # shape. Assert the schema once (cached) before trusting any output; on a
    # mismatch, retrieval is disabled for the process — no degraded canon.
    if not _schema_ok(settings.poggio_bin):
        return []

    world_root = Path(data_dir).parent
    raw: list[dict] = []

    location = (getattr(world_context, "current_location", "") or "").strip()
    if location and location.lower() != "nowhere":
        raw += _run_recipe(
            settings.poggio_bin,
            world_root,
            "at-location",
            ["--location", location],
            _SCENE_LIMIT,
        )

    action = (player_action or "").strip()
    if action:
        raw += _run_recipe(
            settings.poggio_bin,
            world_root,
            "established",
            ["--text", action],
            _ESTABLISHED_LIMIT,
        )

    # Dedup by id (scene entities kept ahead of established turns), cap total.
    seen: set[str] = set()
    lean: list[dict[str, Any]] = []
    for hit in raw:
        proj = _project(hit)
        if proj is None or proj["id"] in seen:
            continue
        seen.add(proj["id"])
        lean.append(proj)
        if len(lean) >= _TOTAL_CAP:
            break
    return lean


def _run_recipe(
    poggio_bin: str,
    world_root: Path,
    recipe: str,
    extra: list[str],
    limit: int,
) -> list[dict]:
    """Run one poggio recipe → its list of hits, or ``[]`` on any failure."""
    cmd = [
        poggio_bin,
        "query",
        "--world",
        str(world_root),
        "--recipe",
        recipe,
        "--limit",
        str(limit),
        *extra,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            # poggio emits UTF-8 JSON; decode it as UTF-8 regardless of the
            # host locale (Windows defaults to CP1252, which would mangle
            # non-ASCII lore/names — gemini-high on PR #165). errors="replace"
            # keeps a stray byte from raising, preserving fail-open.
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_S,
            check=True,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # OSError covers FileNotFoundError (poggio not on PATH); SubprocessError
        # covers non-zero exit + timeout; ValueError covers a decode error.
        # Fail-open.
        logger.warning("lorekeeper: poggio %s failed (fail-open): %s", recipe, exc)
        return []
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        logger.warning(
            "lorekeeper: poggio %s returned bad JSON (fail-open): %s", recipe, exc
        )
        return []
    return data if isinstance(data, list) else []


def _project(hit: object) -> dict[str, Any] | None:
    """Validate + pass through one poggio v0.2.0 **lean** hit.

    RFC-0012: poggio now emits the lean shape ``{id, kind, name, source,
    snippet}`` directly (entity name/description + turn label + source-side
    truncation are all poggio's job now), so this is a pass-through — no
    derivation, no re-truncation. It keeps only the defensive guard: ``id``
    must be a non-empty string (it's the dedup key — a non-scalar would raise
    ``TypeError: unhashable`` outside the per-recipe try and break fail-open;
    poggio v0.2.0 guarantees string ids, but this is untrusted external output).
    ``name``/``snippet`` are coerced to ``str`` and default gracefully.
    """
    if not isinstance(hit, dict):
        return None
    hid = hit.get("id")
    if not isinstance(hid, str) or not hid:
        return None
    return {
        "id": hid,
        "kind": hit.get("kind", "?"),
        "name": str(hit.get("name") or hid),
        "source": hit.get("source", ""),
        "snippet": str(hit.get("snippet") or ""),
    }


def _schema_ok(poggio_bin: str) -> bool:
    """True if the poggio binary reports the schema this fold expects.

    RFC-0012 deploy-safety: probe ``poggio schema-version`` once per process
    (cached) and require exactly ``_EXPECTED_SCHEMA``. A wrong/old/missing
    binary (mismatch, non-zero exit, decode error, not on PATH) → ``False``,
    logged once, and retrieval is disabled for the process — fail-open loud, so
    a bad install yields no canon rather than a mis-shaped (slug-name) block.
    The probe needs no trellis.
    """
    cached = _schema_ok_cache.get(poggio_bin)
    if cached is not None:
        return cached
    ok = False
    try:
        proc = subprocess.run(
            [poggio_bin, "schema-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_SCHEMA_TIMEOUT_S,
            check=True,
        )
        version = (proc.stdout or "").strip()
        ok = version == _EXPECTED_SCHEMA
        if not ok:
            logger.warning(
                "lorekeeper: poggio schema-version %r != expected %r — retrieval "
                "DISABLED for this process (fail-open loud)",
                version,
                _EXPECTED_SCHEMA,
            )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning(
            "lorekeeper: poggio schema-version probe failed — retrieval DISABLED "
            "for this process (fail-open loud): %s",
            exc,
        )
    _schema_ok_cache[poggio_bin] = ok
    return ok
