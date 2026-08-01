# RFC 0018 — Engine-authoritative derived maxes (ADR-0004 Slice 1b)

**Status:** Implemented
**Date:** 2026-07-27
**Author:** Russell Pfister; Claude Code
**Implements:** ADR-0004 (state truthfulness) Slice 1b; `docs/BACKLOG.md` → "ADR-0004 Slice 1b — engine-authoritative derived HP/magic"
**Supersedes:** the derived-vitality deferral in [RFC-0017](0017-progression-enforcement.md) § Out of Scope
**Follow-up:** ADR-0004 Slice 1c (DM archetype mapping for free-text classes) — `docs/BACKLOG.md`

---

## Context

[RFC-0017](0017-progression-enforcement.md) (Slice 1) made `level` + `stats`
engine-authoritative but **deferred the derived vitality** — `hp.max` and
`magic_pool.max` — leaving them prompt-applied (the DM wrote them on a level-up).
Two blockers forced that deferral; this RFC resolves both.

1. **The class HP factor had no code home.** `max HP = Body × class_HP_factor`
   (Warrior 8 / Rogue 6 / Mage 4 / Cleric 6) lived only as prose in the class
   module's `prompt.md`. No module shipped machine-readable rules data — schema
   fragments are contracts, not data.
2. **A formula conflict.** RFC-0009's prompt said `hp.max += class_HP_factor` on
   *every* level-up; the combat module (`combat/hp-pool-v1`, the HP owner) said
   `max HP = Body × factor` — HP grows only when **Body** is raised. Those disagree.

The derivations, confirmed in the modules:
- `hp.max = Body × class_HP_factor` (`combat/hp-pool-v1` + the class module).
- `magic_pool.max = Will × 2` (`magic/realm-pool-v1`, casters only).
- `hp` / `magic_pool` are `{current, max}`; `current` fluctuates with damage /
  casting (narrative) — only the **max** is a pure derivation.

## Decisions (resolved)

- **D1 — factor home: a module rules-data file.** The class module ships a
  machine-readable `rules.json`; an engine loader reads it. This establishes the
  **first "module provides machine-readable rules data" pattern** (ADR-0005-aligned:
  the class module owns its rules; combat/magic/progression read them).
- **D2 — HP formula: pure `Body × factor`.** RFC-0009's flat `+= factor` was the
  wrong one and is corrected. HP grows **only when Body is the raised stat**.
- **D3 — scope: maxes engine-owned every PC op; currents narrative-owned.** The
  maxes are deterministic from the engine-owned stats + the class factor, so a DM
  can never inflate them; forced on every PC op like `stats`. On a level-up that
  grows a max, the engine bumps `current` by the same delta; otherwise `current`
  is untouched. Non-casters get no `magic_pool`. Clamping `current ≤ max` is a
  combat-lane follow-up (out of scope).
- **D4 — the combat/magic prompt-math migration is folded in.** The prompts drop
  the *player's* max-derivation (the engine owns it); they keep the narrative
  machinery and **NPC** hp/pool guidance (NPC maxes stay DM-authored).

### Free-text class → fail-safe (not in the original draft)

The PC `class` field is free-text and often not one of the four archetype keys
(`Sal` = `Proctor`, `Chez` = `chaingang boss`). The engine derives a max **only
when** the world's bound class module supplies a factor for the PC's class
(case-insensitive); otherwise it leaves `hp.max`/`magic_pool.max` DM-authored —
exactly the pre-RFC-0018 behavior. Deriving a max is opt-in on a *known* class,
never a guessed fallback. Closing that gap — the DM classifying a flavor class
into the nearest archetype at establishment, stored as an engine-pinned
`archetype` handle — is **Slice 1c**, a fast-follow.

## Implementation

- **Rules-data + loader.** `engine/modules/class/four-class-fantasy-v1/rules.json`
  (`{archetype: {hp_factor, magic}}`); the manifest gains an optional `rules_data`
  field; `ModuleManifest`/`LoadedModule` carry it; `load_module` reads + JSON-parses
  it (ManifestError on missing/malformed/non-object). `assembly.resolve_active_module`
  resolves a world's bound module for a subsystem (defaults-layered).
- **`engine/class_rules.py`** — the IO boundary: resolve a world's class module,
  load its rules-data, look up the PC's class (case-insensitive) → `{hp_factor,
  magic}` or None (fail-safe; never raises). Keeps `progression` pure.
- **`engine/progression.py`** — `authoritative_maxes(stats, class_rules)` (pure:
  `hp_max = Body × factor`; `magic_pool_max = Will × 2` for casters; None where
  unresolvable). `enforce_progression` gains a `class_rules` kwarg and, when a max
  resolves, forces `hp.max` / `magic_pool.max` on every PC op, bumping `current`
  by the growth delta (or seeding `current = max` on first establishment) via
  `_apply_max`; a DM-inflated max is overridden with a player notice. Deep-merge
  preserves currents + siblings; the maxes computed once against the stored sheet
  so multiple same-turn PC ops stay deterministic.
- **`backend/routes/stream.py`** — resolves the PC's class rules once, threads
  them into the every-turn `enforce_progression` and (on a level-up) the SSE hint
  mirror, so the grown maxes show live.
- **Prompts** — the progression prompt drops the derived-max math; combat + magic
  drop the *player's* max-derivation (keep NPC guidance + all narrative
  machinery); the class prompt notes the player's `hp.max` is engine-owned.

## Placement contract (ADR-0004)

Engine computes (`progression.authoritative_maxes`, pure) → backend injects at the
`stream.py` dispatch seam (`enforce_progression`) → the fs-manager write boundary
is unchanged. The maxes take mechanism (a) (dispatch-recompute-and-inject) for the
same reason `level`/`stats` do: the authorized and hallucinated writes are
byte-identical `<world_update>` ops, so a write-boundary guard can't tell them
apart. See the ADR-0004 hunt-list entry.

## Testing

- `tests/engine/test_progression_maxes.py` — `authoritative_maxes` per-class +
  non-caster + fail-safe; enforce forces maxes every PC op; the growth delta
  current-bump (full + wounded); Will-raise grows the pool not HP; non-caster gets
  no `magic_pool`; DM-inflated max overridden + notice; first-establishment seeds
  `current = max`; class-unresolved leaves the DM max.
- `tests/engine/test_class_rules.py` — case-insensitive lookup, free-text miss,
  non-string/empty, cleared subsystem, no-rules-data module, unknown module.
- `tests/engine/test_modules.py` — manifest `rules_data` parse; the real class
  module ships rules-data; loader error branches (missing / malformed / non-object).

## Out of Scope

- Clamping `current ≤ max` every turn (combat lane).
- The DM free-text → archetype mapping (Slice 1c).
- NPC progression / maxes; non-Fantasy class sets.

## Cross-links

- ADR-0004; RFC-0017 (Slice 1 — this completes its deferred derived-vitality
  half); RFC-0007 (`hp-pool-v1`, `Body × factor`); RFC-0008 (`realm-pool-v1`,
  `Will × 2`); ADR-0005 (the module-provides-rules-data pattern D1 introduces).
- `docs/BACKLOG.md` → ADR-0004 Slice 1b (resolved) + Slice 1c (filed).
