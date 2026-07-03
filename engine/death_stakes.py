"""Death-stakes enforcement — RFC-0014, ``combat`` subsystem.

Pure functions: no filesystem, no network, no LLM. The backend orchestration
(``backend/routes/stream.py``) calls these with the loaded ``WorldContext`` and
the resolve-turn roll, then dispatches the (possibly overridden) payload through
``engine.apply_world_update``. Keeping the logic here — not in the DM prompt and
not in fs-manager — is the point of the RFC: the engine, not the DM, commits the
outcome of a death save, and the ``permadeath`` gate lives where the world's
flag + stored state are both known.

Two enforcements:

1. :func:`resolve_death_save` — engine-authoritative outcome (RFC-0014 Q1 = 2a).
   Recomputes the margin server-side from the validated d100 ``rolled`` + the
   *stored* ``will`` stat (tamper-proof: the client's ``total``/``margin`` are
   ignored so a crafted roll can't dodge death), advances or resets the
   three-strike clock, and decides ``unconscious`` vs ``dead``.
2. :func:`enforce_permadeath` — drops any payload update that would revive a
   character whose *stored* status is ``dead`` when the world's ``permadeath``
   flag is set, returning a DM-facing rejection instead of silently honoring it.

The character JSON shape these read/write (per ``base-v1`` + ``hp-pool-v1``):
``{"name", "status": "alive|unconscious|dead|...", "role": "player|npc|...",
"module_data": {"character_sheet": {"stats": {"will": N}, "hp": {"current": N}},
"combat": {"death_saves_failed": 0..3}}}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Reuse the Fact-Extractor's slug transform rather than re-deriving it — a second
# copy is the "sibling-path drift" hazard (a slug rule change in one place would
# silently mis-target the other). Both are pure engine code.
from engine.agents.fact_extractor import _slugify as _slugify_entity

# The death-save contract (RFC-0007 `hp-pool-v1`, made authoritative here).
DEATH_SAVE_TARGET = 60  # Moderate — fixed for death saves, not DM-chosen.
DEATH_CLOCK_MAX = 3  # Three failed saves → dead.
_STAT_MULTIPLIER = 5  # d100 + stat×5, mirroring apps/sentinel-ui/src/utils/roll.js.

_REVIVABLE_STATUSES = {"alive", "unconscious", "unknown", "missing"}


@dataclass(frozen=True)
class DeathSaveOutcome:
    """The committed result of one death save. ``failed`` is the new clock."""

    failed: int
    status: str
    stabilized: bool
    died: bool
    margin: int


def recompute_margin(rolled: int, will: int, target: int = DEATH_SAVE_TARGET) -> int:
    """Server-side death-save margin from the *validated* d100 + *stored* stat.

    Deliberately ignores the client-supplied ``total``/``margin`` (only ``rolled``
    is server-validated 1–100). Open-ended surge/fumble is not applied to death
    saves — it would require trusting a second client roll, and the point here is
    a tamper-proof consequence, not maximal drama.
    """
    return rolled + will * _STAT_MULTIPLIER - target


def resolve_death_save(
    *, rolled: int, will: int, current_failed: int
) -> DeathSaveOutcome:
    """Compute the authoritative death-save outcome from a real roll + stored state.

    ``margin >= 0`` stabilizes (clock reset, stays ``unconscious``); otherwise the
    clock advances, and the third failure is ``dead``.
    """
    margin = recompute_margin(rolled, will)
    if margin >= 0:
        return DeathSaveOutcome(
            failed=0, status="unconscious", stabilized=True, died=False, margin=margin
        )
    new_failed = max(0, current_failed) + 1
    if new_failed >= DEATH_CLOCK_MAX:
        return DeathSaveOutcome(
            failed=DEATH_CLOCK_MAX,
            status="dead",
            stabilized=False,
            died=True,
            margin=margin,
        )
    return DeathSaveOutcome(
        failed=new_failed,
        status="unconscious",
        stabilized=False,
        died=False,
        margin=margin,
    )


def find_player_character(
    characters: list[dict[str, Any]], player_name: str
) -> dict[str, Any] | None:
    """Locate the player's character entity: prefer ``role == "player"``, else name."""
    for char in characters:
        if str(char.get("role", "")).lower() == "player":
            return char
    lowered = (player_name or "").strip().lower()
    if not lowered:
        return None
    for char in characters:
        if str(char.get("name", "")).strip().lower() == lowered:
            return char
    return None


def stored_will(character: dict[str, Any]) -> int:
    """Read the stored ``will`` stat (0 if absent — a statless PC can't win a save)."""
    stats = ((character.get("module_data") or {}).get("character_sheet") or {}).get(
        "stats"
    ) or {}
    try:
        return int(stats.get("will", 0))
    except (TypeError, ValueError):
        return 0


def stored_death_clock(character: dict[str, Any]) -> int:
    """Read the stored death-save clock (0 if absent)."""
    combat = (character.get("module_data") or {}).get("combat") or {}
    try:
        return max(0, int(combat.get("death_saves_failed", 0)))
    except (TypeError, ValueError):
        return 0


def _entities_op_matches(op: dict[str, Any], name: str) -> bool:
    """True if this update op targets the named character's entity file."""
    if str(op.get("operation")) != "update":
        return False
    target = str(op.get("target_file", ""))
    if "/entities/" not in target:
        return False
    data = op.get("data")
    if (
        isinstance(data, dict)
        and str(data.get("name", "")).strip().lower() == (name or "").strip().lower()
    ):
        return True
    slug = _slugify_entity(name) if name else None
    return bool(slug) and target.endswith(f"/entities/{slug}.json")


def apply_death_outcome(
    payload: dict[str, Any], *, player_name: str, outcome: DeathSaveOutcome
) -> dict[str, Any]:
    """Override the payload so the PC's committed ``status`` + death clock win.

    Mutates the PC's existing update op if the DM emitted one (so the engine's
    status/clock beat the DM's), else appends a minimal merge-update op. fs-manager
    applies ``operation: "update"`` as a merge, so a partial ``data`` is enough.
    Returns the same payload object for convenience.
    """
    updates = payload.setdefault("updates", [])
    op = next((o for o in updates if _entities_op_matches(o, player_name)), None)
    if op is None:
        slug = _slugify_entity(player_name)
        if slug is None:
            return payload  # nothing we can safely target
        op = {
            "target_file": f"data/state/core/entities/{slug}.json",
            "operation": "update",
            "data": {"name": player_name},
        }
        updates.append(op)
    data = op.setdefault("data", {})
    if not isinstance(data, dict):
        return payload
    data["status"] = outcome.status
    module_data = data.setdefault("module_data", {})
    if isinstance(module_data, dict):
        combat = module_data.setdefault("combat", {})
        if isinstance(combat, dict):
            combat["death_saves_failed"] = outcome.failed
    return payload


def enforce_permadeath(
    payload: dict[str, Any],
    *,
    stored_characters: list[dict[str, Any]],
    player_name: str,
    permadeath: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Refuse to revive a stored-``dead`` PC when ``permadeath`` is set.

    Drops any status-revival or HP-restore field from the PC's update op and
    returns a DM-facing rejection per drop. A no-op unless permadeath is on and
    the PC's *stored* status is already ``dead`` — dying this turn is not revival.
    """
    rejections: list[str] = []
    if not permadeath:
        return payload, rejections
    pc = find_player_character(stored_characters, player_name)
    if pc is None or str(pc.get("status", "")).lower() != "dead":
        return payload, rejections

    name = str(pc.get("name") or player_name)
    for op in payload.get("updates", []):
        if not _entities_op_matches(op, name):
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            continue
        new_status = str(data.get("status", "")).lower()
        if new_status in _REVIVABLE_STATUSES:
            data.pop("status", None)
            rejections.append(
                f"permadeath: {name} is dead — status cannot be changed to "
                f"'{new_status}'. Revival refused; narrate the death as final."
            )
        # HP restore: the legacy flat `health` and module hp.current both count.
        if _pops_positive(data, "health"):
            rejections.append(
                f"permadeath: {name} is dead — HP cannot be restored. Revival refused."
            )
        hp = (data.get("module_data") or {}).get("character_sheet", {})
        if isinstance(hp, dict) and _pops_positive(hp.get("hp") or {}, "current"):
            if not rejections or "HP cannot be restored" not in rejections[-1]:
                rejections.append(
                    f"permadeath: {name} is dead — HP cannot be restored. "
                    "Revival refused."
                )
    return payload, rejections


def _pops_positive(data: dict[str, Any], key: str) -> bool:
    """If ``data[key]`` is a positive number, remove it and report the drop."""
    if not isinstance(data, dict) or key not in data:
        return False
    try:
        value = float(data[key])
    except (TypeError, ValueError):
        return False
    if value > 0:
        data.pop(key, None)
        return True
    return False
