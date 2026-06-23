"""DM-prompt assembly from a world's active module set (ADR-0005 / RFC-0005).

``build_dm_prompt(modules)`` walks the world's active modules in a fixed
canonical order and concatenates each module's prompt-fragment
contribution into one system prompt. The order is hard-coded (not
dict-iteration order) so the assembled prompt is deterministic +
diffable regardless of how the ``modules`` map was built.

RFC-0005 ships only ``core/base-v1`` (subsystem ``base``), so
``build_dm_prompt(DEFAULT_MODULES)`` returns exactly the base module's
content — which is the former ``DM_SYSTEM_PROMPT`` verbatim. Mechanic
modules (RFC-0006+) slot into later positions and append their
fragments; the base fragment always leads.
"""

from __future__ import annotations

from .loader import load_module

# The core default module set — what a vanilla world runs, and the
# fallback when a world has no explicit `modules` map (legacy worlds
# created before the field existed). Grows as RFCs add subsystems:
#   RFC-0005: base
#   RFC-0006 Slice 1: character_sheet (four stats; no rolls yet)
#   RFC-0006 Slice 2: resolution (the d100 roll loop) — NOT YET
DEFAULT_MODULES: dict[str, str] = {
    "base": "core/base-v1",
    "character_sheet": "core/four-stat-v1",
}

# Deterministic assembly order. A module fills its subsystem's slot; the
# assembled prompt walks this list, not the `modules` dict's iteration
# order, so the output is stable. `base` always leads (invariant DM
# personality + STATE DISCIPLINE). The mechanic subsystems are ordered
# foundation-first (resolution → sheet → class → combat → magic →
# progression) then ambient (time, tension). Subsystems not yet shipped
# are listed so later RFCs slot in without reshuffling.
CANONICAL_SUBSYSTEM_ORDER: tuple[str, ...] = (
    "base",
    "resolution",
    "character_sheet",
    "class",
    "combat",
    "magic",
    "progression",
    "time",
    "tension",
)


def build_dm_prompt(modules: dict[str, str] | None = None) -> str:
    """Assemble the DM system prompt for a world's active module set.

    Parameters
    ----------
    modules
        ``{subsystem: module_name}`` for the world. ``None`` (or an empty
        map) falls back to ``DEFAULT_MODULES`` — the path legacy worlds
        and the back-compat ``DM_SYSTEM_PROMPT`` constant take.

    Returns
    -------
    str
        The composed system prompt: each active module's prompt fragment,
        in CANONICAL_SUBSYSTEM_ORDER, joined by a blank line. Subsystems
        present in ``modules`` but absent from the canonical order are
        ignored (with no crash) — a forward-compat guard so an unknown
        subsystem key can't break assembly.

    The world's ``modules`` map is layered ON TOP of ``DEFAULT_MODULES``
    rather than replacing it: a world that names some subsystems but omits
    others (notably ``base`` — the invariant DM personality, which must
    always be present per ADR-0005) still gets the core defaults for the
    omitted slots. A world overrides a subsystem only by naming it
    explicitly. A non-dict ``modules`` (malformed config) falls back to
    the defaults rather than crashing. (codex P2 + gemini-medium, PR #144.)
    """
    overrides = modules if isinstance(modules, dict) else {}
    active = {**DEFAULT_MODULES, **overrides}
    fragments: list[str] = []
    for subsystem in CANONICAL_SUBSYSTEM_ORDER:
        module_name = active.get(subsystem)
        if not module_name:
            continue
        loaded = load_module(module_name)
        if loaded.prompt_fragment_text:
            fragments.append(loaded.prompt_fragment_text)
    return "\n\n".join(fragments)
