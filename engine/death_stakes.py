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
from engine.identity import _identity_key

# The death-save contract (RFC-0007 `hp-pool-v1`, made authoritative here).
DEATH_SAVE_TARGET = 60  # Moderate — fixed for death saves, not DM-chosen.
DEATH_CLOCK_MAX = 3  # Three failed saves → dead.
_STAT_MULTIPLIER = 5  # d100 + stat×5, mirroring apps/sentinel-ui/src/utils/roll.js.


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


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it's a dict, else an empty dict.

    A malformed-input guard: world state is LLM-emitted, so ``module_data`` /
    ``character`` may be well-formed JSON of the WRONG type (a list, string,
    null). Chaining ``.get`` through this degrades instead of raising
    ``AttributeError`` (gemini-high on PR #172; the malformed-LLM-output hunt
    pattern)."""
    return value if isinstance(value, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` onto a copy of ``base`` (dict values only)."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_player_character(
    characters: list[dict[str, Any]], player_name: str
) -> dict[str, Any] | None:
    """Locate the player's character entity by STABLE IDENTITY.

    The session's ``player_character_name`` is the anchor: when it's supplied we
    match on the entity **slug** — the same ``_slugify`` the Fact-Extractor uses to
    build an op's target path, so punctuation variants (``O'Neil`` / ``O Neil``,
    both ``o_neil.json``) still resolve — and we do **NOT** fall back to
    ``role == "player"``.

    Why the role scan can't be trusted once we know the name: characters load in
    ``sorted(glob("*.json"))`` FILENAME order, ``fact_extractor`` passes ``role``
    through and upserts to a NEW slug, and fs-manager writes an absent target — so a
    hallucinated ``<world_update>`` introducing ``0-imposter`` with ``role:"player"``
    sorted first and BECAME the PC. Its name/slug differ from the session PC, so
    ``enforce_progression`` never matched it, and it could carry ``level: 5``, maxed
    stats, derived maxes and any archetype — bypassing every RFC-0017/0018/0019
    invariant through the shadow. Minting is separately blocked by
    ``engine.identity.enforce_pc_identity``; this is the resolution half.

    A name with no ASCII slug characters (``李``) still anchors — it compares
    casefolded rather than degrading to "no identity", which would hand the session
    back to the first ``role:"player"`` entity (codex). The role scan survives only
    for the genuinely-unknown-name case. Returning None
    (nothing matches yet) is normal and safe — enforcement no-ops, which is already
    what happens in production for a world whose DM never wrote a PC entity.
    """
    if not isinstance(characters, list):
        return None
    key = _identity_key(player_name)
    if key:
        for char in characters:
            if not isinstance(char, dict):
                continue
            if _identity_key(char.get("name")) == key:
                return char
        return None
    # No session PC name to anchor on — legacy path.
    for char in characters:
        if isinstance(char, dict) and str(char.get("role", "")).lower() == "player":
            return char
    return None


def stored_will(character: dict[str, Any] | None) -> int:
    """Read the stored ``will`` stat (0 if absent/malformed — a statless PC can't win)."""
    stats = _as_dict(
        _as_dict(
            _as_dict(_as_dict(character).get("module_data")).get("character_sheet")
        ).get("stats")
    )
    try:
        return int(stats.get("will", 0))
    except (TypeError, ValueError):
        return 0


def stored_death_clock(character: dict[str, Any] | None) -> int:
    """Read the stored death-save clock (0 if absent/malformed)."""
    combat = _as_dict(_as_dict(_as_dict(character).get("module_data")).get("combat"))
    try:
        return max(0, int(combat.get("death_saves_failed", 0)))
    except (TypeError, ValueError):
        return 0


def _entities_op_matches(op: dict[str, Any], name: str) -> bool:
    """True if this update op targets the named character's entity file."""
    if not isinstance(op, dict):
        return False
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
    payload: dict[str, Any],
    *,
    player_name: str,
    outcome: DeathSaveOutcome,
    stored_module_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make the engine's committed ``status`` + death clock the authoritative PC write.

    Two subtleties, both real breaks the PR bots caught (PR #172):

    - fs-manager applies ``update`` as a SHALLOW top-level merge
      (``existing.update(data)``), so writing a *partial* ``module_data`` would
      ERASE the stored ``character_sheet`` (stats/HP) — after one save the PC's
      ``will`` reads 0. We therefore write the FULL ``module_data``: the stored
      sheet deep-merged with the op's own same-turn changes, then our clock.
    - The Fact-Extractor can emit MULTIPLE ops for one entity, executed in order,
      so a later DM op could re-``alive`` a rolled ``dead``. We set the committed
      status + clock on EVERY matching op (the last therefore wins), appending one
      if the DM emitted none.

    Returns the same payload object for convenience.
    """
    if not isinstance(payload, dict):
        return payload
    updates = payload.get("updates")
    if not isinstance(updates, list):
        updates = []
        payload["updates"] = updates
    base_md = _as_dict(stored_module_data)
    matching = [o for o in updates if _entities_op_matches(o, player_name)]
    if not matching:
        slug = _slugify_entity(player_name)
        if slug is None:
            return payload  # nothing we can safely target
        op = {
            "target_file": f"data/state/core/entities/{slug}.json",
            "operation": "update",
            "data": {"name": player_name},
        }
        updates.append(op)
        matching = [op]
    for op in matching:
        if not isinstance(op, dict):
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            data = {}
            op["data"] = data
        data["status"] = outcome.status
        # Full module_data so the shallow fs-manager merge preserves the sheet:
        # stored sheet <- this op's same-turn module_data <- our death clock.
        merged = _deep_merge(base_md, _as_dict(data.get("module_data")))
        combat = _as_dict(merged.get("combat"))
        combat["death_saves_failed"] = outcome.failed
        merged["combat"] = combat
        data["module_data"] = merged
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
    if not (permadeath and isinstance(payload, dict)):
        return payload, rejections
    pc = find_player_character(stored_characters, player_name)
    if pc is None or str(pc.get("status", "")).lower() != "dead":
        return payload, rejections

    name = str(pc.get("name") or player_name)
    updates = payload.get("updates")
    if not isinstance(updates, list):
        return payload, rejections
    for op in updates:
        if not isinstance(op, dict):
            continue
        data = op.get("data")
        if not isinstance(data, dict):
            continue
        # Match the PC's own entity file, OR any entities-update that RE-INTRODUCES
        # the player under a new name (a rename/clone dodges the name+slug match —
        # swarm MEDIUM on PR #172). There is one player and they are dead, so any
        # entities op claiming role "player" is a revival attempt.
        claims_player = (
            str(op.get("operation")) == "update"
            and "/entities/" in str(op.get("target_file", ""))
            and str(data.get("role", "")).lower() == "player"
        )
        if not (_entities_op_matches(op, name) or claims_player):
            continue
        # Status is an ALLOWLIST, not a denylist (gemini/swarm HIGH on PR #172):
        # only `dead` may stand on a stored-dead PC. Enumerating revival words
        # ('alive', 'unconscious', …) let prose-y statuses ('stable', 'conscious',
        # 'recovering') slip through — and the frontend renders anything != 'dead'
        # as living, a full revival. Drop any non-empty status that isn't 'dead'.
        new_status = str(data.get("status", "")).lower()
        if new_status and new_status != "dead":
            data.pop("status", None)
            rejections.append(
                f"permadeath: {name} is dead — status cannot be changed to "
                f"'{new_status}'. Revival refused; narrate the death as final."
            )
        # HP restore (flat `health`, module hp.current AND hp.max) + a death-clock
        # reset are all revival-adjacent writes to a dead PC — drop them all.
        char_sheet = _as_dict(_as_dict(data.get("module_data")).get("character_sheet"))
        hp = _as_dict(char_sheet.get("hp"))
        hp_restored = _pops_positive(data, "health")
        hp_restored = _pops_positive(hp, "current") or hp_restored
        hp_restored = _pops_positive(hp, "max") or hp_restored
        combat = _as_dict(_as_dict(data.get("module_data")).get("combat"))
        clock_written = combat.pop("death_saves_failed", None) is not None
        if hp_restored or clock_written:
            rejections.append(
                f"permadeath: {name} is dead — HP / death clock cannot be "
                "restored. Revival refused."
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
