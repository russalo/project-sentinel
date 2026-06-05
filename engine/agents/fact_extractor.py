"""Fact-Extractor agent — bridges DM narrative and fs-manager schema.

Takes a raw DM response (narrative text plus an embedded `<world_update>`
hint block in the ORM-flavored shape the DM prompt emits) and produces an
`apply_world_update.schema.json`-valid payload that fs-manager will accept.

This is the canonical bridge between the two `<world_update>` shapes in
the repo:

1. The DM prompt emits a hint block like
   `{"world": {...}, "characters": [...], "locations": [...], ...}` —
   this is ORM-flavored convenience structure for the LLM, not a
   filesystem-operation contract.

2. `schemas/apply_world_update.schema.json` defines the contract
   fs-manager enforces:
   `{session_id, log_entry, updates: [{target_file, operation, data}]}`.

The Fact-Extractor walks (1) and produces (2). It does not call
fs-manager and does not read or write any world-state files. It does
self-validate as a sanity check, and that self-validation lazily loads
`schemas/apply_world_update.schema.json` from disk on first use via
`engine.schema.validate()` — a one-time initialization read, not a
runtime side effect. If its own output fails schema validation,
something is wrong with this module, not the caller.

Path layout
-----------
Entity types map onto `data/state/core/<category>/<slug>.json`:

- characters → data/state/core/entities/<slug>.json
- locations  → data/state/core/locations/<slug>.json
- factions   → data/state/core/factions/<slug>.json
- items      → data/state/core/items/<slug>.json
- world      → data/state/core/world/state.json (single global file)

Slugs are derived from entity names via a conservative transform:
lowercase, replace non-`[a-zA-Z0-9_-]` runs with `_`, strip leading
and trailing underscores. Entries that slugify to empty are skipped
with an error.

Operation choice
----------------
Every entry uses `operation: "update"`. fs-manager's update handler
merges with existing JSON if present, or writes fresh if not — exactly
upsert semantics. Using `create` would fail on existing entities;
knowing which applies requires reading current state, which the
Fact-Extractor deliberately does not do (pure function, no I/O).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..schema import validate

# Regex for pulling the <world_update>...</world_update> block out of
# raw DM text. Matches the same pattern backend/api/dm_ai.py used, so
# this Fact-Extractor is a drop-in replacement for the current inline
# parse logic.
_BLOCK_PATTERN = re.compile(r"<world_update>([\s\S]*?)</world_update>")

# Allowed characters in a slugified name — must match the filename
# component of the path regex in schemas/apply_world_update.schema.json.
_SLUG_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]+")

# log_entry bounds from schemas/apply_world_update.schema.json
_LOG_ENTRY_MIN = 10
_LOG_ENTRY_MAX = 4000


@dataclass
class FactExtractResult:
    """Outcome of a Fact-Extractor run.

    `payload` is None when there is nothing to dispatch:
    - the DM emitted no `<world_update>` block
    - the block was malformed JSON
    - every entry in the block slugified to empty or was unusable
    - the constructed payload failed schema self-validation

    `narrative` always contains the prose portion with the
    `<world_update>` block stripped out, even when payload is None.
    The player still gets to see the story beat.

    `errors` lists any non-fatal parse issues encountered. Callers
    can log these for debugging but should not treat an empty-errors
    result as "succeeded" — check `payload is not None` for that.
    """

    payload: dict[str, Any] | None
    narrative: str
    errors: list[str] = field(default_factory=list)


def extract(
    raw_response: str,
    session_id: str,
    turn_number: int,
    confidence: float | None = None,
) -> FactExtractResult:
    """Parse a DM response into a schema-valid apply_world_update payload.

    Parameters
    ----------
    raw_response
        The full DM response text — narrative plus an optional
        `<world_update>` JSON hint block.
    session_id
        UUID string of the active session. Passed through to the
        payload's `session_id` field. The schema enforces `format: uuid`
        on this, so an invalid UUID will surface as a self-validation
        error at the end of extraction.
    turn_number
        Zero-based turn counter for the current session. Passed through
        to `metadata.turn_number`.
    confidence
        Optional Fact-Extractor confidence score in [0.0, 1.0]. Passed
        through to `metadata.confidence` when provided.

    Returns
    -------
    FactExtractResult
        `payload` is a schema-valid apply_world_update dict ready to
        pass to `engine.apply_world_update(config, payload)` — or None
        when extraction produced nothing worth dispatching. Always
        check `payload is not None` before dispatching.
    """
    narrative = _strip_world_update_block(raw_response)
    errors: list[str] = []

    blocks = _extract_blocks(raw_response)
    if not blocks:
        return FactExtractResult(payload=None, narrative=narrative, errors=errors)

    # Process every block the DM emitted. In normal operation the DM
    # prompt instructs a single block at the end, but the narrative
    # stripper removes *all* blocks via re.sub(), so if the LLM ever
    # emits more than one we must see them all here — otherwise the
    # later blocks get hidden from the player AND silently lost from
    # state, which is the worst possible outcome.
    if len(blocks) > 1:
        errors.append(
            f"found {len(blocks)} <world_update> blocks; DM prompt expects 1. "
            f"Processing all of them in order."
        )

    updates: list[dict] = []
    for block_index, block in enumerate(blocks):
        try:
            hint = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"world_update block {block_index} is not valid JSON: {exc}")
            continue

        if not isinstance(hint, dict):
            errors.append(
                f"world_update block {block_index} is {type(hint).__name__}, "
                f"expected object"
            )
            continue

        updates.extend(_build_updates(hint, errors))

    if not updates:
        return FactExtractResult(payload=None, narrative=narrative, errors=errors)

    log_entry = _build_log_entry(narrative, session_id, turn_number)

    metadata: dict[str, Any] = {
        "agent": "fact-extractor",
        "turn_number": turn_number,
    }
    if confidence is not None:
        metadata["confidence"] = confidence

    # Namespace authorization is NO LONGER set here (red-team #7): the
    # fact_extractor has no business deciding authorization scope, and a value
    # in the LLM-parsed body could be a self-asserted escalation. The scope is a
    # trusted query param the backend sets on dispatch (default "core" for the
    # canonical world-write path) — see engine.apply_world_update(namespace=…)
    # and fs-manager's validate_namespace. So `namespace` is intentionally absent
    # from the payload body (and from the schema).
    payload: dict[str, Any] = {
        "session_id": session_id,
        "log_entry": log_entry,
        "updates": updates,
        "metadata": metadata,
    }

    validation = validate(payload)
    if not validation.ok:
        errors.extend(f"self-validation failed: {msg}" for msg in validation.errors)
        return FactExtractResult(payload=None, narrative=narrative, errors=errors)

    return FactExtractResult(payload=payload, narrative=narrative, errors=errors)


# ── helpers ──────────────────────────────────────────────────────────


def _extract_blocks(raw: str) -> list[str]:
    """Return every <world_update> block in raw response order.

    The DM prompt expects exactly one block, but the narrative stripper
    removes all of them — so returning a list here keeps the extractor
    consistent with the stripper and prevents silent data loss if the
    LLM ever emits multiple blocks.
    """
    return [match.group(1).strip() for match in _BLOCK_PATTERN.finditer(raw)]


def _strip_world_update_block(raw: str) -> str:
    return _BLOCK_PATTERN.sub("", raw).strip()


def _slugify(name: str) -> str | None:
    """Produce a filename-safe slug matching the schema's path regex.

    Returns None for names that reduce to empty. Callers should treat
    None as "skip this entry and log an error."
    """
    if not isinstance(name, str):
        return None
    slug = _SLUG_SANITIZE.sub("_", name.lower()).strip("_")
    return slug or None


def _strip_action(entry: dict) -> dict:
    """Remove the DM's `action` field from an entry; it is not part
    of the stored entity and is only a hint to the Fact-Extractor."""
    return {k: v for k, v in entry.items() if k != "action"}


def _build_updates(hint: dict, errors: list[str]) -> list[dict]:
    """Walk the DM hint block and produce updates[] entries.

    The hint is expected to be a dict with any subset of these keys:
    `world` (dict), `characters` (list), `locations` (list),
    `factions` (list), `items` (list). Unknown top-level keys are
    ignored with a warning.
    """
    updates: list[dict] = []

    category_map = {
        "characters": "entities",
        "locations": "locations",
        "factions": "factions",
        "items": "items",
    }

    # World block → single file at data/state/core/world/state.json
    world = hint.get("world")
    if world is not None:
        if isinstance(world, dict) and world:
            updates.append(
                {
                    "target_file": "data/state/core/world/state.json",
                    "operation": "update",
                    "data": world,
                }
            )
        elif not isinstance(world, dict):
            errors.append(f"world block is {type(world).__name__}, expected object")

    # Entity collections → one file per named entity
    for hint_key, category in category_map.items():
        entries = hint.get(hint_key)
        if entries is None:
            continue
        if not isinstance(entries, list):
            errors.append(
                f"{hint_key} block is {type(entries).__name__}, expected list"
            )
            continue

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(
                    f"{hint_key}[{index}] is {type(entry).__name__}, expected object"
                )
                continue

            name = entry.get("name")
            slug = _slugify(name) if name is not None else None
            if slug is None:
                errors.append(f"{hint_key}[{index}] missing usable name (got {name!r})")
                continue

            updates.append(
                {
                    "target_file": f"data/state/core/{category}/{slug}.json",
                    "operation": "update",
                    "data": _strip_action(entry),
                }
            )

    # Warn on unknown top-level keys so prompt drift is visible
    known = {"world", "characters", "locations", "factions", "items"}
    for unknown in set(hint.keys()) - known:
        errors.append(f"unknown top-level key in world_update block: {unknown!r}")

    return updates


def _build_log_entry(narrative: str, session_id: str, turn_number: int) -> str:
    """Derive a schema-compliant log_entry from the narrative.

    Schema requires minLength=10, maxLength=4000. Short narratives are
    prefixed with a session/turn tag. Long narratives are truncated
    with an ellipsis.
    """
    entry = narrative.strip() or "(no narrative emitted)"
    if len(entry) < _LOG_ENTRY_MIN:
        prefix_source = session_id[:8] if session_id else "session"
        entry = f"[session {prefix_source} turn {turn_number}] {entry}".strip()
    if len(entry) > _LOG_ENTRY_MAX:
        entry = entry[: _LOG_ENTRY_MAX - 3] + "..."
    return entry
