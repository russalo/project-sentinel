# RFC 0009 — Progression module

**Status:** Implemented
**Date:** 2026-06-24
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005, fifth (and final v0.1) mechanic slice —
milestone-based, player-enacted character advancement, against
Fantasy-flagship v0.1 Axis 4 (ratified 2026-06-24).
**Supersedes:** —

---

## Where this sits

Under ADR-0005, after RFC-0008 (magic). One module:
`core/milestone-v1` (subsystem **progression**). It completes the Fantasy
core ruleset — the seven-module default set (base, resolution,
character_sheet, class, combat, magic, progression).

Progression is the axis with the sharpest **ownership** constraint
(Russell, 2026-06-24): *"Experience should dictate level; everything else
was set at creation and only changeable by events and outcomes of players'
choices — which means the AI DM's court."* The character's level and
attributes are the **player's** to change. The DM may PROPOSE growth at an
earned beat; it may never write a `level` or raise a `stats` value on its
own initiative. This is the same wall ADR-0004 (state truthfulness,
deferred) reserves a number for, applied to the one place a DM most often
overreaches — the 2026-04-15 turn-4 bug levelled a character 1→2 for a
cosmetic illusion. The module's prompt makes the wall explicit; the
plumbing makes enacting a level-up a deliberate player act.

## Ratified decisions (2026-06-24)

- **Milestone, not XP.** No point counter to drift. The DM proposes a
  level-up at a genuine narrative beat; there is no experience number to
  track or mis-add.
- **Player-enacted, DM-proposed.** The DM emits a `level_up: {to_level}`
  signal and STOPS. A UI affordance (the LevelUpCard) lets the player pick
  which attribute to raise; the choice resends and the DM applies exactly
  that package. The DM never picks the stat.
- **Level-up affordance is UI** (not free-text): a dedicated card mirroring
  the RFC-0006 CheckRequestRail, so the choice is unambiguous and the wire
  payload is structured.
- **HP grows every level too** (not stats-only): max HP rises by the
  character's class HP factor each level (Warrior 8 / Rogue 6 / Cleric 6 /
  Mage 4 — the RFC-0007 factors), and `current` rises with it.
- **+1 stat point per level, player's pick** (cap 10). Derived values
  follow: raising Will grows a caster's `magic_pool.max` (Will × 2).
- **Levels 1–5 in v0.1**; higher tiers deferred.

## Proposal

### 1. `core/milestone-v1` (subsystem: progression)

Prompt-fragment module (`manifest.toml` + `prompt.md`), `requires`
`core/four-stat-v1` + `core/four-class-fantasy-v1` (it reads stats + the
class HP factor). No new schema fragment — it writes the existing
`module_data.character_sheet` fields (`level`, `stats`, `hp`,
`magic_pool`).

**Prompt teaches:**
- **Propose at earned beats only** — surviving a deadly encounter,
  resolving a major arc, a hard-won discovery. Never trivial/cosmetic;
  paced a few beats per level.
- **Propose by emitting** `"level_up": { "to_level": N }` in the
  `world_update` block, framing it in the narrative, then STOPPING — do
  not change level/stats that turn.
- **The player's choice is sovereign** — never write `level` or raise a
  `stats` value unilaterally; only apply growth the player has enacted.
- **Apply** (on a `LEVEL-UP CHOICE` in the turn input): `level` → N; the
  chosen attribute +1 (cap 10); `hp.max += class_HP_factor` and `current`
  up by the same; caster `magic_pool.max` re-derives if Will was raised.
  Apply ONLY the chosen stat.

### 2. The proposal → enact loop (mirrors the d100 roll loop)

The shape is RFC-0006's check loop with a different signal:

- **Engine** — `DMTurnInput.level_up: dict | None`; `_level_up_block`
  renders a `LEVEL-UP CHOICE:` block into the user message naming exactly
  the player's chosen stat (tolerant of a missing stat → no block).
  Threaded through `_build_messages` at both `run_turn` and `stream_turn`
  call sites, alongside the existing `roll`.
- **Backend** — `LevelUpChoice` model (`stat`, `to_level`);
  `StreamRequest.level_up`; the stream route threads
  `body.level_up.model_dump()`.
- **Frontend** — `chatStore.levelUp` (+ `setLevelUp` validating
  `to_level`, mirroring the `setCheckRequest` hardening; + `clearLevelUp`).
  `useDMStream` reads `event.data.level_up` into the store, clears it at
  turn start (parallel to `checkRequest`), and exposes `sendLevelUp(stat,
  toLevel, sessionId)` (a resolve-style turn carrying the choice).
  `LevelUpCard` (sibling of `CheckRequestRail` above the command bar)
  renders the proposal: four stat buttons showing the current → next value
  (a stat at the cap is disabled + marked "max"), a Confirm that locks the
  turn, logs a scroll line, and resends.

### 3. DEFAULT_MODULES + re-baseline

`DEFAULT_MODULES` grows to the seven-module set (… + `progression`).
Assembly test re-baselines (derived from fragments); base-fragment
integrity intact.

## Acceptance Criteria

- [x] `core/milestone-v1` module: manifest (`requires` four-stat +
      four-class) + prompt (propose / sovereignty wall / apply package).
- [x] Engine: `DMTurnInput.level_up`; `_level_up_block`; threaded through
      both `_build_messages` call sites.
- [x] Backend: `LevelUpChoice` + `StreamRequest.level_up` + stream route.
- [x] Frontend: `chatStore.levelUp` (+ validated setter); `useDMStream`
      signal read + `sendLevelUp`; `LevelUpCard`; CommandBar wiring.
- [x] `DEFAULT_MODULES` += progression; assembly re-baselined to seven;
      base integrity intact.
- [x] Tests: engine (level-up block render + omit), module load + default
      set, chatStore setter hardening, LevelUpCard behavior.
- [x] RFC 0009 lands Implemented; README index + Blueprint KB manifest
      updated.

## Out of Scope

- **Stat-point cost / multi-point allocation** — one stat +1 per level in
  v0.1; budgets/respec deferred.
- **Levels beyond 5** — higher tiers + the curve are a later slice.
- **Spell learning / new abilities on level-up** — HP + one stat in v0.1;
  expanding a caster's repertoire on advance is deferred.
- **XP/point tracking** — explicitly rejected (drift surface).
- **Backend/fs-manager enforcement of the sovereignty wall** — v0.1
  enforces it in the prompt; a hard schema/dispatch guard against the DM
  writing `level`/`stats` outside an enacted choice is the ADR-0004
  (state truthfulness) lane — deferred, number reserved.
- **Class-restricted stat picks** — any stat in v0.1.

## Cross-links

- ADR-0005; RFC-0006 (the check loop this mirrors + the `module_data.
  character_sheet` it writes); RFC-0007 (the class HP factors HP growth
  uses); Fantasy-flagship v0.1 Axis 4.
- ADR-0004 (state truthfulness, deferred) — the reserved number for the
  hard-enforcement version of the sovereignty wall.
