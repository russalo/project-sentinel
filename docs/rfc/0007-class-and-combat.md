# RFC 0007 — Class + combat modules

**Status:** Implemented
**Date:** 2026-06-24
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005, third mechanic slice — the four Fantasy classes
+ the combat loop, against the Fantasy-flagship v0.1 design (Axes 3 + 5)
with the combat decisions ratified 2026-06-24.
**Supersedes:** —

---

## Where this sits

Under ADR-0005, after RFC-0006 (resolution + character sheet). Two
modules:

- `core/four-class-fantasy-v1` — subsystem **class**
- `core/hp-pool-v1` — subsystem **combat**

**Combat reuses the RFC-0006 d100 roll loop entirely** — an attack is a
Body check vs the enemy's Defense (a `check_request` + roll), so this RFC
adds *no new roll infrastructure*. The work is: two prompt modules, the
HP-model migration (PlayerVitals reads the sheet's hp), and `DEFAULT_MODULES`
growth.

## Ratified decisions (2026-06-24)

- **Combat flow: round-per-roll.** Each combat turn = one attack roll
  (a Body check vs the target's Defense); the margin resolves that
  round's exchange. No per-swing rolls, no separate initiative.
- **Damage: hybrid (weapon die + margin).** On a hit, damage = weapon
  die + a margin nudge. Weapon identity AND how-well-you-hit both matter.
- **HP: sheet hp, % display.** `max = Body × class_HP_factor`; stored at
  `module_data.character_sheet.hp.{current,max}`; PlayerVitals renders
  `current/max` as its fill. The flat 0–100 `health` field retires
  (with a transition fallback).

## Proposal

### 1. `core/four-class-fantasy-v1` (subsystem: class)

Prompt-fragment module (the character's `class` is already a top-level
entity field; this module supplies the *mechanical definitions*, the
same for every character of a class — so it's rules, not per-character
state). Teaches the four classes:

| Class | Stat priority | HP factor | Magic | Signature (1–2 moves) |
|---|---|---|---|---|
| **Warrior** | Body | 8 | none | Press the attack (extra damage on a solid hit); Guard (raise Defense a round) |
| **Rogue** | Body, Mind | 6 | none | Strike from shadow (big margin bonus when unseen); Slip away (escape check advantage) |
| **Mage** | Will, Mind | 4 | arcane (RFC-0008) | (spells — magic module) |
| **Cleric** | Will, Heart | 6 | divine (RFC-0008) | (spells + heal — magic module) |

- The **HP factor** is the number combat + the sheet use for
  `max = Body × factor` (Warrior Body 6 → 48; Mage Body 3 → 12).
- Magic access is named here but the casting mechanics are RFC-0008.
- Signature moves are light v0.1 — narrative affordances the DM can
  invoke, not a deep ability tree.
- Weapon/armor are judged from the fiction (a dagger → 1d4, a longsword
  → 1d8; worn plate → a Defense bonus). No equipment schema in v0.1 —
  the DM reads the gear the character is described wielding.

### 2. `core/hp-pool-v1` (subsystem: combat)

Prompt-fragment module. Teaches:

**HP.** Every combat-capable character has
`module_data.character_sheet.hp = {current, max}` where
`max = Body × class_HP_factor`. Set it the first time a character enters
combat (or on creation). `current` is DM-writable (damage/healing);
`max` is system-derived (changes only with Body/level).

**Attack (round-per-roll).** When the player attacks in combat, the DM
requests a **Body check vs the target's Defense** (`Defense = 40 +
Body×3 + armor`) — the existing `check_request`/roll loop. The margin
resolves the round:
- `margin < 0` — miss (the worse, the more the enemy capitalizes).
- `margin ≥ 0` — hit; the margin feeds damage.
- open-ended high → a devastating blow; open-ended low → you're exposed.

**Damage (hybrid).** On a hit:
`damage = weapon_die + ⌊margin / 10⌋`
- weapon_die by size: light **1d4**, medium **1d6**, heavy **1d8**,
  two-handed **1d10** (DM picks from the wielded weapon).
- the margin nudge: +1 per full 10 of margin (margin +22 → +2). A
  decisive hit hits harder; a barely-hit does weapon-die only.
- *(The frontend already rolls the d100 for the attack; the weapon die
  can be rolled the same client-side way OR the DM rolls it narratively
  — see Open Q1.)*

**Damage application + death.** `current -= damage`, clamped at 0.
- `current` reaches 0 → `status = unconscious` (RFC-0001 pose).
- While unconscious at 0 HP, each turn the DM may call a **death save**
  (a Will check vs Moderate 60); a fail advances a 3-strike death clock,
  a success stabilizes, any healing reverses it. Three fails → `dead`
  (the skull pose). `dead` also on unambiguous narration (decapitation,
  etc.) — the harder commitment, as today.

### 3. HP-model migration (frontend)

`PlayerVitals.jsx` currently reads the flat `health` field (0–100) for
its fill. Migrate it to read `module_data.character_sheet.hp`:
- fill fraction = `current / max` (variable max per character).
- the eight bands (Whole/Bruised/.../Dead) key off the **fraction**, not
  a 0–100 number.
- **Transition fallback:** a character with no `module_data.character_sheet.hp`
  yet (created before this RFC, not yet in combat) falls back to the flat
  `health/100`. So existing worlds keep rendering until the DM populates
  the sheet hp on first combat. The flat field retires once every active
  character has sheet hp.

### 4. DEFAULT_MODULES + re-baseline

`DEFAULT_MODULES` grows to `{base, resolution, character_sheet, class,
combat}` (canonical order already has class before combat). The
assembly test re-baselines to the new five-fragment default (derived
from the fragments, as before). Base-fragment migration integrity
unchanged.

## Open Questions

1. **Who rolls the weapon die? → FRONTEND (ratified 2026-06-24).** All
   randomness stays client-side. `check_request` carries `weapon_die`
   (the "1dN" spec); the frontend rolls it alongside the d100 and sends
   `weaponDie`/`weaponRoll` in the roll payload; the DM computes
   `damage = weapon_roll + ⌊margin/10⌋`. The reveal shows the weapon die.
2. **Margin-nudge divisor → `⌊margin/10⌋`** (v0.1 starting value; tunable
   post-playtest).
3. **Death-save → Will vs Moderate 60, 3 strikes** (v0.1; tunable).
4. **One PR** — combat reused the roll loop, so the work was two prompt
   modules + weapon-die plumbing + the PlayerVitals migration; shipped as
   a single PR.

## Acceptance Criteria

- [ ] `core/four-class-fantasy-v1` (class) + `core/hp-pool-v1` (combat)
      modules: manifests + prompts.
- [ ] `DEFAULT_MODULES` grows to the five-module set; assembly test
      re-baselined; base-fragment integrity intact.
- [ ] PlayerVitals reads `module_data.character_sheet.hp` (fraction-based
      bands) with the flat-`health` transition fallback; tests updated.
- [ ] If OQ1=(a): `weaponDie` threaded through check_request + roll
      (engine/backend/frontend), reveal shows the weapon die.
- [ ] RFC 0007 lands Implemented; README index + the Blueprint KB
      manifest (`docs/blueprint-kb-manifest.txt`) updated with the new
      RFC path.

## Out of Scope

- **Magic / spell combat** (Mage/Cleric casting) — RFC-0008.
- **Equipment schema** (formal weapon-size / armor fields) — DM judges
  from fiction in v0.1.
- **Initiative / multi-combatant turn order** beyond round-per-roll.
- **Progression** (how HP/stats grow) — RFC-0009.
- **Crit/fumble tables** — open-ended + margin remain the drama.
- **NPC full sheets** — NPCs get HP + Defense (+ the DM picks numbers by
  threat); not full four-stat sheets.

## Cross-links

- ADR-0005; RFC-0006 (resolution + sheet — the roll loop combat reuses);
  RFC-0001 (PlayerVitals poses combat drives); Fantasy-flagship v0.1
  Axes 3 + 5.
- Downstream: RFC-0008 (magic) consumes `magic_pool` + the class magic
  access; RFC-0009 (progression) grows HP/stats.
