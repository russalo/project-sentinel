# RFC 0006 — Resolution + character-sheet modules

**Status:** Accepted (Slice 1 of 2 implemented)
**Date:** 2026-06-23
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005 (subsystem modularity), second slice — the first
*mechanic* modules, against the Fantasy-flagship v0.1 design ratified
2026-06-23 (d100 open-ended resolution; four-stat 1–10 character sheet).
**Supersedes:** —
**Superseded by:** —

---

## Implementation status

Shipped in two slices (a single drop would strand players — the DM
emitting check-requests with no frontend roller to answer them breaks
live turns):

- **Slice 1 (this landing) — stats foundation.** `core/four-stat-v1` +
  `character_sheet` in `DEFAULT_MODULES` + the module's schema fragment +
  the stat-grounding prompt rule + tests. The DM tracks four stats per
  significant character and grounds them in fiction. **No rolls yet** —
  resolution stays narrative, so nothing strands. Safe on live worlds
  (adds stat-tracking; the existing flat `health` field + PlayerVitals
  are untouched). RFC status: **Accepted**.
- **Slice 2 (next) — the roll loop.** `core/d100-open-v1` + the
  `check_request` field + frontend roller/reveal + `resolution` joins
  `DEFAULT_MODULES` + the schema-enforcement seam. Flips RFC status to
  **Implemented**.

---

## Where this sits

RFC-0005 shipped the module plumbing (manifest, loader, registry,
`build_dm_prompt` assembly, `module_data.<subsystem>` namespacing
convention) + `core/base-v1`, with zero gameplay change. RFC-0006 ships
the first two **mechanic** modules onto that plumbing:

- `core/d100-open-v1` — subsystem **resolution**
- `core/four-stat-v1` — subsystem **character_sheet**

This is the **first non-zero-change RFC** — it gives the DM a real check
mechanic and characters real stats. Subsequent RFCs (0007 class+combat,
0008 magic, 0009 progression) build on the stats + roll contract this
establishes.

## Context

The 2026-06-23 design session ratified two foundational decisions:

- **Resolution: d100 open-ended.** `total = d100 + (stat × 5) +
  situational mods` vs a target. `margin = total − target` drives degree
  of success. Open-ended: nat 96–00 reroll-and-add, nat 01–05
  reroll-and-subtract. Targets: Easy 40 / Moderate 60 / Hard 80 / Very
  Hard 100.
- **Character sheet: four stats, 1–10.** Body / Mind / Heart / Will. The
  stat → d100 bridge is `× 5` (a 1–10 stat → +5..+50 bonus).

Both numbers (×5 multiplier, 40/60/80/100 bands, open-ended thresholds)
were confirmed as the v0.1 starting values (tunable via playtest).

This RFC turns those decisions into two modules + the frontend roller +
the first real `module_data` schema.

## Proposal

### 1. `core/four-stat-v1` (subsystem: character_sheet)

**Module dir:** `engine/modules/character_sheet/four-stat-v1/`
(`manifest.toml` + `prompt.md` + `schema.json`).

**State shape — the first real `module_data` payload.** A character
entity gains:

```json
"module_data": {
  "character_sheet": {
    "stats": { "body": 7, "mind": 5, "heart": 4, "will": 8 },
    "hp": { "current": 56, "max": 56 },
    "defense": 61,
    "magic_pool": { "current": 16, "max": 16 }
  }
}
```

- `stats` — the four 1–10 attributes. **Player-owned** (set at creation;
  the ADR-0004 boundary, when that lands, marks these immutable to the
  DM).
- `hp` — `max = body × class_HP_factor`; `current` is DM-writable
  (narrative damage). *(class_HP_factor comes from the class module,
  RFC-0007; until then four-stat ships a default factor of 6.)*
- `defense` — `40 + (body × 3) + armor_bonus`; the d100 target an
  attacker must beat. Armor bonus is 0 until the combat module (RFC-0007).
- `magic_pool` — `max = will × 2`; only meaningful for casters (magic
  module, RFC-0008), but the field is defined here so the sheet is whole.

**Schema enforcement — the deferred RFC-0005 piece lands here.** RFC-0005
established `module_data.<subsystem>` as a *convention* (no enforcement,
because no entity schema existed). RFC-0006 ships the first
`schema_fragment`: a JSON Schema for `module_data.character_sheet`
(stats are ints 1–10; hp/magic_pool are `{current, max}` non-negative
ints; defense a non-negative int). The fs-manager validates writes to a
character entity's `module_data.character_sheet` against it. **This
requires the entity-schema work RFC-0005 punted** — see Open Question 1.

**Prompt fragment** teaches the DM: the four stats and what each governs;
that stats are the basis for resolution rolls (Body for physical, Mind
for mental, Heart for social, Will for magic/resolve); that it must NOT
rewrite player stats (narrate consequences, not stat edits) — a soft
prompt wall now, hardened by ADR-0004 later.

### 2. `core/d100-open-v1` (subsystem: resolution)

**Module dir:** `engine/modules/resolution/d100-open-v1/`
(`manifest.toml` + `prompt.md`).

**Prompt fragment** teaches the DM the full mechanic:

- When an action's outcome is *uncertain and consequential*, call for a
  check: name the **governing stat** (body/mind/heart/will) and a
  **target** (Easy 40 / Moderate 60 / Hard 80 / Very Hard 100).
- The frontend rolls; the DM receives `{stat, rolled, bonus, mods,
  total, target, margin, open_ended}` and resolves from the **margin**:
  margin < 0 = failure (worse the more negative); 0–9 = scrapes it;
  10–29 = solid; 30+ = decisive; open-ended high = a surge beyond
  intent; open-ended low = a fumble spiral.
- Trivial / safe actions don't roll — the DM just narrates.
- The margin is the narrative-intensity dial: scale the prose to it.

**No state of its own** — resolution is a prompt-fragment-only module
(no `module_data`, no `schema_fragment`). It reads stats from the
character_sheet module's state and consumes the frontend's roll.

### 3. Frontend d100 roller — DM-requested two-step (RATIFIED)

**Flow (ratified 2026-06-23): DM-requested, two-step.** Player sends an
action → if the outcome is uncertain + consequential, the DM responds
with a **check request** (governing stat + target) instead of resolving
→ the frontend surfaces a Roll affordance → the player clicks Roll → the
frontend rolls d100 **client-side** (real randomness, not LLM bias),
computes `total = d100 + stat×5 + mods`, and auto-resends the turn with
the roll result → the DM resolves from the margin. Stat + target are
fixed *before* the die, so there's no after-the-fact fudge.

The DM signals a check request through a structured field in its
`world_update` block (e.g. `check_request: {stat, target, prompt}`),
parallel to how `suggestedActions` already rides the block — so the
frontend can render the request affordance deterministically rather than
scraping prose.

### 3a. Roll display — the three beats (RATIFIED)

A dice game must *show the dice*; the roll reveal is the trust anchor
(players won't trust an LLM "you fail," they trust a number they watched
land — which is also why the roll is client-side). The two-step flow
gives rolls a real visible moment:

**Beat 1 — check request.** Renders above the command bar, a sibling of
the action-pill rail (same visual family):

```
🎲  BODY check — Hard (80)          [ Roll ]
    "Can you force the seized portcullis?"
```

**Beat 2 — the reveal.** **Click-to-roll** (ratified — the physical-dice
ritual is half the appeal, and pairs with the explicit request). A
**static reveal with a quick count-up** (ratified for v0.1; a fuller
rolling-dice animation is a deferred polish pass):

```
        d100  ⟶  47
      + Body  ⟶  +30  (stat 6 ×5)
      ─────────────────
        total ⟶  77   vs  Hard 80
        margin   −3   ✦ near miss
```

Open-ended rolls get a flourish: a 96–00 reroll-and-add shows the surge
stacking; a 01–05 shows the fumble spiral.

**Beat 3 — result in the scroll.** Lands as a delta-message (the
existing system-log component family — same idiom as "Russalo took 8
damage"), so turn history reads back cleanly:

```
🎲 Body vs Hard 80 — 77 (margin −3): near miss
```

Then the DM's resolving narrative streams below it.

**Deferred (not v0.1):** a dedicated dice-history panel (the scroll's
delta-messages already are the history); a full rolling-dice animation.

### 4. DEFAULT_MODULES + rollout — Every world (RATIFIED)

**Ratified 2026-06-23: the modules go into `DEFAULT_MODULES`.** Sentinel
becomes a d100 RPG everywhere on the deploy that ships RFC-0006 —
including existing alpha worlds (the Trog playthrough), which start using
the mechanic mid-stream. Rationale: the alpha exists to test new systems;
maximize exposure. `DEFAULT_MODULES` grows to:

```python
DEFAULT_MODULES = {
    "base": "core/base-v1",
    "resolution": "core/d100-open-v1",
    "character_sheet": "core/four-stat-v1",
}
```

Two consequences this RFC must handle:

- **Re-baseline the RFC-0005 equivalence test.** `build_dm_prompt()` is
  no longer the base-only prompt — it now legitimately assembles base +
  resolution + character_sheet. The byte-identity-to-pre-RFC-0005 test
  gets a NEW frozen expectation (the full default-set prompt); the
  *mechanism* (assembly composes the active set in canonical order) is
  unchanged and still tested. This is the expected, intended change — the
  first time the assembled default prompt grows.
- **Backfill stats for live characters.** Existing entities (e.g. Trog's
  `Russalo`) have no `module_data.character_sheet`. On the first d100
  turn in a world whose characters lack stats, the engine seeds default
  stats so a roll has a stat to read. Two options: (i) the DM seeds them
  on first reference (a prompt rule: "if a character has no stats,
  establish them now from the fiction"); (ii) the backend seeds a default
  array when it loads a character missing the sheet. **Leaning (i)** —
  the DM grounding stats in the established fiction reads better than a
  flat default array, and it's a prompt rule not a migration. Confirm at
  implementation.

## Resolved (2026-06-23)

- **Roll flow** → DM-requested two-step (§3).
- **Roll display** → three-beat: request affordance → click-to-roll →
  static reveal with quick count-up → delta-message in scroll (§3a).
  Animated dice + dice-history panel deferred.
- **Rollout** → every world; `DEFAULT_MODULES` grows (§4).

## Open Questions (resolve at implementation)

1. **Entity-schema enforcement seam.** RFC-0005 found there's no
   stored-entity schema — only the fs-manager *payload* schema (freeform
   `data`). To validate `module_data.character_sheet`, fs-manager needs
   to validate the *entity* shape on writes to
   `data/state/core/entities/*.json`. Smallest version: a per-module
   `schema_fragment` that fs-manager applies to `module_data.<subsystem>`
   sub-objects when the write targets an entity file. **Leaning: the
   per-module fragment** — modular-by-construction. (Implementation
   detail; doesn't change the design.)
2. **Live-character stat backfill** → leaning DM-seeds-from-fiction on
   first reference, not a backend default array (§4). Confirm at
   implementation.
3. **Stat allocation at creation:** point-buy, fixed array, or
   class-suggested defaults? **Leaning class-suggested defaults the
   player can adjust** — lowest friction. (WorldCreation surface.)
4. **class_HP_factor before the class module:** four-stat ships a default
   factor of 6 so the sheet is functional standalone; RFC-0007's class
   module overrides it. (Leaning: ship the default.)

## Acceptance Criteria

- [ ] `engine/modules/character_sheet/four-stat-v1/` — manifest + prompt
      + `schema.json` for `module_data.character_sheet`.
- [ ] `engine/modules/resolution/d100-open-v1/` — manifest + prompt.
- [ ] fs-manager validates `module_data.character_sheet` writes against
      the module's schema fragment (entity-schema seam, OQ1).
- [ ] Frontend rolls d100 client-side + threads the result to the DM;
      the roll + margin surface in the turn delta.
- [ ] Rollout wired per the §4 decision (DEFAULT vs opt-in + the
      `world.modules` write if opt-in).
- [ ] Prompt-assembly tests updated for the new default/opt-in set;
      RFC-0005 equivalence property preserved or explicitly re-baselined.
- [ ] WorldCreation stat allocation (OQ4).
- [ ] RFC 0006 lands Implemented in the same PR(s); README indexes
      updated.

## Out of Scope

- **Combat** (attack rolls, damage, death) — RFC-0007. This RFC defines
  `defense` + the roll contract combat will use, but not the combat loop.
- **Magic** casting / pool depletion — RFC-0008 (the pool field is
  defined here; spending it is not).
- **Progression** (how stats grow) — RFC-0009.
- **Class HP factors / armor bonuses** beyond defaults — RFC-0007.
- **ADR-0004 hard enforcement** of player-owned stats — the prompt wall
  ships here; the structural wall is the state-truthfulness track.
- **Crit / fumble tables** — open-ended high/low + margin are the v0.1
  drama; tables are a deferred RM-depth pass.

## Cross-links

- ADR-0005 (subsystem modularity) — the architecture
- RFC-0005 (module foundation) — the plumbing this builds on; the
  `module_data` enforcement it deferred lands here
- Fantasy-flagship v0.1 design, Axes 1–2 (ratified 2026-06-23)
- Sibling track: ADR-0004 (state truthfulness) — will harden the
  player-owned-stats prompt wall into a structural one
- Downstream: RFC-0007 (class+combat) consumes `defense` + the roll
  contract; RFC-0008 (magic) consumes `magic_pool`; RFC-0009
  (progression) grows `stats`
