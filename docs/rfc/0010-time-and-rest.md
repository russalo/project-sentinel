# RFC 0010 — Time & Rest module

**Status:** Implemented
**Date:** 2026-06-30
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005, the `time` subsystem — a bounded day cycle plus
the rest mechanic that makes non-magical recovery real. Fantasy-flagship
core systems, the next slice after the v0.1 seven-module set.
**Supersedes:** —

---

## Where this sits

Under ADR-0005, after RFC-0009 (progression). One module:
`core/time-cycle-v1` (subsystem **time**, the slot already reserved in
`CANONICAL_SUBSYSTEM_ORDER`). It grows the default set to eight (base,
resolution, character_sheet, class, combat, magic, progression, time).

It closes a concrete gap the ambient surfaces exposed. Combat (RFC-0007)
*drains* HP and magic (RFC-0008) *can* restore it, but a player without a
healer had **no grounded recovery** — and the magic module already
references "long rest → full pool / short rest → half" with no system
defining what a rest *is*. The HP silhouette (PR #127) made the question
unavoidable: when HP drops, "how do I heal?" got an improvised, session-
inconsistent answer. This module makes rest the non-magical recovery path
and lights up the dormant `time` slot it depends on.

## Ratified decisions (2026-06-30)

- **Bounded day cycle.** `world.timeOfDay` moves through a fixed loop
  `dawn → morning → midday → afternoon → dusk → night`, wrapping to dawn;
  `world.day` (integer, from 1) increments on the wrap. No free-form time
  string to drift.
- **Time advances on time-consuming action, not per turn.** Travel,
  extended tasks, and rest move the cycle one+ blocks; an in-scene
  exchange does not. Fiction-driven but bounded to the cycle.
- **Short rest** — advances ~one block; restores `+⌊hp.max / 4⌋` HP
  (clamped) and brings the magic pool to at least half. A breather between
  encounters; needs a moment's safety, not a bed.
- **Long rest** — a full night; sets `timeOfDay` to `morning` and
  `world.day += 1`; restores HP and magic pool to full and clears
  temporary conditions. Needs a **safe-enough place** (DM-judged) — not
  mid-dungeon, mid-pursuit, or with a threat bearing down.
- **Rest recovers the living only.** It does not revive the dead and does
  not replace the combat module's death-save loop for an unconscious
  character at 0 HP. Recovery is bounded — no double short rest to
  over-heal, no full heal without the night a long rest costs.
- **The magic pool refresh references rest defined here** — this module is
  now the authority for the "long → full / short → half" the magic prompt
  already leans on; the two stay consistent.

## Proposal

### 1. `core/time-cycle-v1` (subsystem: time)

Prompt-fragment module (`manifest.toml` + `prompt.md`), `requires`
`core/four-stat-v1` + `core/hp-pool-v1` + `core/realm-pool-v1` (it
restores the sheet `hp`/`magic_pool` and coordinates with combat's drain +
magic's refresh). **No new schema fragment** — it writes the existing
`module_data.character_sheet.{hp,magic_pool}` fields and the world's
`timeOfDay` / `day`, mirroring how combat (RFC-0007) is prompt-only and
writes the existing sheet fields.

**Prompt teaches:**
- **The cycle** — the six bounded `timeOfDay` blocks, the `day` counter,
  and that time advances on a time-consuming action (travel / extended
  task / rest), not every turn.
- **Short rest** — `+⌊hp.max / 4⌋` HP (clamp at max), magic pool up to at
  least half; advances one block; minimal safety.
- **Long rest** — HP + pool to full, clear temporary conditions; sets
  `timeOfDay` to `morning`, `day += 1`; needs a safe-enough place.
- **Boundaries** — recovers the living, never revives the dead or bypasses
  the death-save loop; bounded rates; emit the recovered `hp.current` /
  `magic_pool.current` (and advanced `timeOfDay` / `day`) in the
  `world_update` block, the same way combat emits damage.

### 2. DEFAULT_MODULES + assembly

`DEFAULT_MODULES` grows to the eight-module set (… + `time`). The `time`
slot was already present in `CANONICAL_SUBSYSTEM_ORDER` (after
progression, before the unshipped `tension`), so assembly slots it in
without reshuffling. The back-compat `DM_SYSTEM_PROMPT` constant
(`build_dm_prompt()`) picks it up automatically.

## Acceptance Criteria

- [x] `core/time-cycle-v1` module: manifest (`requires` four-stat +
      hp-pool + realm-pool) + prompt (cycle / short rest / long rest /
      boundaries).
- [x] `DEFAULT_MODULES` += `time`; assembly composes it last (before the
      unshipped `tension`); base integrity intact.
- [x] Tests: `test_time_module_loads`; default-assembly-order updated to
      eight; `test_default_modules_is_eight_core_set`.
- [x] RFC 0010 lands Implemented in the same PR as the module.

## Out of Scope

- **Weather & environment effects** (`world.weather` rules) — a later
  slice; this module only governs time + rest.
- **Encounter mechanics** — monster templates + the encounter scaffold are
  a separate RFC; the `tension` slot stays unshipped.
- **Exhaustion / fatigue accumulation, hunger / thirst** — no resource
  attrition in v1; long rest "clears temporary conditions" is narrative,
  not a tracked counter.
- **Time-of-day combat / skill modifiers** (night stealth, dawn penalties)
  — the cycle is tracked and felt; mechanical hooks off it are deferred.
- **A dedicated time-of-day UI widget** — `timeOfDay` / `day` changes
  already surface as deltas in the System Log; a panel surface is a
  follow-up.
- **Schema/dispatch enforcement of the cycle enum + recovery bounds** —
  v1 enforces them in the prompt (same posture as combat/magic); a hard
  guard is the deferred per-module-schema-enforcement lane (RFC-0006 OQ1).

## Cross-links

- ADR-0005 (subsystem modularity); RFC-0007 (combat — the HP drain this
  recovers, and the prompt-only module shape this mirrors); RFC-0008
  (magic — the pool refresh that references the rest defined here);
  the Core Systems — Fantasy as Flagship Model BACKLOG section
  (healing/recovery + time/calendar items this lands).
