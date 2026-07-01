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

# Slice-1 budget (RFC-0011): scene entities + a bm25 "have we established X?"
# on the action, deduped and capped. Tuned later with real telemetry.
_SCENE_LIMIT = 5
_ESTABLISHED_LIMIT = 3
_TOTAL_CAP = 8
_SNIPPET_MAX = 160
_TIMEOUT_S = 10.0


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
            timeout=_TIMEOUT_S,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # OSError covers FileNotFoundError (poggio not on PATH);
        # SubprocessError covers non-zero exit + timeout. Fail-open.
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
    """Lean-project one poggio hit to ``{id, kind, name, source, snippet}``.

    Consumer-side projection for Slice 1 (Poggio's own lean projection is
    ``poggio#4`` / their v0.2.0). Entity hits carry no ``snippet`` → use the
    ``description``; narrative ("established") hits carry a highlighted
    ``snippet`` + no ``name`` → label them by turn number.
    """
    if not isinstance(hit, dict):
        return None
    hid = hit.get("id")
    if not hid:
        return None
    attrs = hit.get("attrs") if isinstance(hit.get("attrs"), dict) else {}
    kind = hit.get("kind", "?")

    name = attrs.get("name")
    if not name and kind == "turn":
        turn_number = attrs.get("turn_number")
        name = f"prior turn {turn_number}" if turn_number is not None else "prior turn"
    name = name or hid

    snippet = str(hit.get("snippet") or attrs.get("description") or "").strip()
    if len(snippet) > _SNIPPET_MAX:
        snippet = snippet[: _SNIPPET_MAX - 1].rstrip() + "…"

    return {
        "id": hid,
        "kind": kind,
        "name": name,
        "source": hit.get("source", ""),
        "snippet": snippet,
    }
