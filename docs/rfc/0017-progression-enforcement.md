# RFC 0017 — Progression hard-enforcement (ADR-0004 Slice 1)

**Status:** Implemented
**Date:** 2026-07-08
**Author:** Russell Pfister; Claude Code
**Implements:** ADR-0004 (state truthfulness) Slice 1; `docs/BACKLOG.md` → "ADR-0004 Slice 1 — progression hard-enforcement"
**Supersedes:** —

---

## Context

ADR-0004 (state truthfulness, Accepted 2026-07-08) ratified that the engine, not
the DM, owns mechanically-determined state, and named **progression** as its first
hard-enforcement slice. RFC-0009 shipped progression **prompt-only**: the DM is
merely *asked* not to write `level`/`stats` outside an enacted level-up.

A code map of the actual write path turned up three facts that shaped this design:

1. **The authorized write and the attack write were the same path.** Unlike
   death-stakes — where the backend computes the outcome (`death_stakes.resolve_death_save`)
   and *injects* it authoritatively (`apply_death_outcome`), overriding the DM —
   the enacted level-up was applied by the **DM itself** in its `<world_update>`
   and flowed through `fact_extractor` → `apply_world_update` like ordinary state.
   The player's `body.level_up` (`LevelUpChoice`) only rendered a `LEVEL-UP CHOICE`
   prompt block; it never became a verified write. There was **no code-level
   distinction** between "the DM applied the enacted level-up" and "the DM raised
   level/stats on its own."

2. **The attack surface was wide open.** `fact_extractor._strip_action` removes
   only the `action` key; every other character field (a top-level `level`, a
   nested `module_data.character_sheet.stats`) passed through verbatim.

3. **fs-manager cannot enforce this, and there was a latent data-loss bug.**
   `level` is a top-level entity field but `stats` is nested; `check_protected_fields`
   is top-level-only, and the `update` merge is shallow (a partial `module_data`
   write replaces the whole key). Death-stakes survives that by deep-merging
   `stored_module_data`; the level-up path had no such preservation.

## Reclassification: mechanism (a), not (b)

ADR-0004 tentatively slotted progression under **mechanism (b)** (the fs-manager
write-boundary guard). The map shows that is the wrong layer: the authorized and
attack writes are byte-identical (intent isn't in the payload), `stats` is nested
where the top-level guard can't see it, and validating the precise authorized delta
needs the `body.level_up` context fs-manager doesn't have. Progression is a
**mechanism (a)** fit — *dispatch-recompute-and-inject*: the enacted choice is the
trust anchor, the growth is deterministic, and the backend injects it. This RFC
reclassifies it (a) and corrects ADR-0004's example bullet + the BACKLOG item.

## Decisions (locked with Russell 2026-07-08)

1. **Mechanism (a)** — recompute-and-inject, not the (b) fs-manager guard.
2. The engine **computes** the growth (does not validate the DM's arithmetic).
3. An unauthorized DM level/stats write is **stripped with a player-facing SSE
   notice** (parity with the permadeath rejections).
4. **PC-only** for v1. NPC `level`/`stats` stay narrative-owned. *(Known to need
   growth: NPC progression is a future slice, not a permanent exclusion.)*
5. The engine owns the **derived HP/magic bumps too** — but see the scope split:

**Scope split (Option A).** Slice 1 makes **`level` + `stats`** engine-authoritative
— the exact fields RFC-0009's sovereignty wall names. The derived `hp`/`magic_pool`
bumps are **deferred to Slice 1b**: the class HP factor (Warrior 8 / Rogue 6 /
Mage 4 / Cleric 6) and the `max HP = Body × factor` / `magic = Will × 2` derivations
live **only in prompts today** with no code home, and RFC-0009's "hp.max += factor
every level" conflicts with the class module's `Body × factor`. Rather than
duplicate prompt values in code + resolve that formula mid-slice, Slice 1b will give
the class factor a shared code home (with combat/magic) and make HP/magic
engine-authoritative. Until then the DM still applies hp/magic on a level-up, and
this slice **preserves** those DM-written derived fields rather than stripping them.

## Implementation (this PR)

- **`engine/progression.py`** (pure + inject, mirrors `engine/death_stakes.py`):
  `authoritative_progression(cur_level, cur_stats, choice)` computes the committed
  `(level, stats)` — stored (frozen) with no enactment, or with one: `level` =
  **exactly `cur_level + 1`** (the client's `to_level` is advisory only — never
  trusted, so a crafted client can't jump levels) capped at the module max, and the
  chosen stat +1 (capped). `enforce_progression(payload, *, stored_characters,
  player_name, choice)` forces **every** PC entity op's `level` +
  `module_data.character_sheet.stats` to the authoritative value, deep-merging the
  stored `module_data` so siblings (`combat`, `magic`, the DM's hp) survive the
  shallow fs-manager merge on the common turn too; appends a PC op if an enactment
  emitted none; returns SSE notices on a DM override attempt. Matches `update` AND
  `create` ops (defense-in-depth), and fails safe (no enforcement, never a
  force-to-zero) when the PC can't be resolved. PC-scoped; deep-copies the stored
  sheet so the shared read-state isn't mutated.
- **`backend/routes/stream.py`**: at the dispatch seam (beside death-stakes), call
  `enforce_progression` with `body.level_up.model_dump()`; synthesize a minimal
  payload when an enactment lands but the DM emitted no `<world_update>` (extends
  the existing death-outcome fallback); yield each notice as an SSE `error` event.
- **Prompt** (`engine/modules/progression/milestone-v1/prompt.md`): the DM PROPOSES
  (`level_up`) + narrates and **never writes `level`/`stats`** — the engine commits
  them; the DM still applies the derived hp/magic (Slice 1b).

## Open Questions

- [ ] Slice 1b: give the class HP factor a shared code home + make hp/magic
      engine-authoritative + resolve the `+factor` vs `Body × factor` formula.

## Acceptance Criteria

- [x] `authoritative_progression` unit-tested (delta, cap, no-enactment freeze).
- [x] Enacted level-up commits exactly the authorized delta; sibling `module_data`
      (`combat`/`magic`) and the DM's `hp` survive the deep-merge.
- [x] A DM `level`/`stats` write with no enactment is overridden to stored + an SSE
      notice; an over-application on an enacted turn is corrected to the delta.
- [x] Append-on-enactment when the DM emits no PC op; NPC writes untouched; a normal
      PC write (no level/stats) is left untouched; malformed input degrades.
- [x] Progression prompt updated to propose-and-narrate only.
- [x] ADR-0004 example + BACKLOG item corrected to mechanism (a).

## Out of Scope

- **Slice 1b** — derived hp/magic engine-authority + the class-factor code home.
- NPC progression / stat authority (decision 4 — a known future slice).
- **Entity-identity hardening** (red-team follow-up) — an imposter entity that
  sorts before the real PC can *shadow* it in `find_player_character`'s
  first-`role=="player"` resolution. **Correction (codex, PR #186): this IS
  LLM-reachable** — `fact_extractor` passes `role` through and `update`-upserts to a
  new slug, so a hallucinated `<world_update>` can create a `role:"player"` imposter;
  since its name/slug differ from the session PC, `enforce_progression` doesn't match
  it, so the shadow also **bypasses this RFC's level/stats invariant**. Shared with
  death-stakes. This slice enforces on the *session PC's own* entity + fails safe on
  an unresolvable PC, but the shadow + the `None` fail-open need a stable-identity PC
  resolver + a DM-`role:"player"` guard — its own slice (BACKLOG, elevated priority).
- fs-manager entity-schema *shape* enforcement (the authored-but-unenforced
  `four-stat-v1/schema.json`, RFC-0006 OQ1) — validates shape, not authorization.
- XP/point tracking (rejected in RFC-0009).
- Hard-enforcement of other subsystems — later ADR-0004 slices, same shape.

## Cross-links

- ADR-0004 (state truthfulness — the decision this implements; example corrected to
  mechanism (a)).
- RFC-0009 (progression v0.1 — the prompt-only version hardened here), RFC-0014
  (death-stakes — the recompute-and-inject pattern + `stored_module_data` deep-merge
  mirrored), RFC-0007 (class HP factor — Slice 1b's dependency), RFC-0006 (the enact
  loop shape).
- `docs/BACKLOG.md` → ADR-0004 Slice 1 item (this) + the Slice 1b follow-up.
