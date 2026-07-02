# RFC 0013 — Encounter mechanics (`tension` subsystem, `core/encounter-frames-v1`)

**Status:** Implemented
**Date:** 2026-07-02
**Author:** Russell Pfister; Claude Code (origin-core session)
**Implements:** ADR-0005, the `tension` subsystem — the mechanical layer under
the tension meter. Base-v1's TENSION & ENCOUNTER PRESSURE block (PR #124) says
*when* an encounter must land and lists kinds; the combat module said NPCs get
"sensible numbers by their threat level" with no ladder defined. This module
defines **what an encounter mechanically is**. Fantasy-flagship; other genres
re-flavor the tiers, not the frame.
**Supersedes:** — (complements base-v1's tension block; does not move it)

---

## Where this sits

Under ADR-0005, after RFC-0010 (time). One module: `core/encounter-frames-v1`
filling the **reserved `tension` slot** in `CANONICAL_SUBSYSTEM_ORDER` (listed
since RFC-0005 as "ambient (time, tension)" — this is the module it was
reserved for; Russell ratified filling it, 2026-07-02). The default set grows
to **nine** — every reserved slot is now filled. Prompt-fragment module, **no
new schema**: it grounds numbers the combat module already owns and writes
ordinary DM-emitted entity attributes.

Why now: the tension meter signals pressure the DM must release, but each
release was invented from scratch — NPC stats ungrounded, no
surprise/telegraph convention, fleeing narrated arbitrarily, encounters
evaporating without consequence. The silhouette exposed healing's gap
(RFC-0010); the tension meter exposed this one.

## Ratified decisions (2026-07-02)

1. **Five threat tiers, scaled to player level `L`** (Russell: five over
   three — trivial and mythic do real work):

   | Tier | HP | Defense | Damage die | Feel |
   |---|---|---|---|---|
   | trivial | 4×L | 45 | 1d4 | a nuisance; one good hit drops it |
   | standard | 8×L | 50 | 1d6 | a real fight the player should win |
   | dangerous | 12×L | 55 | 1d8 | costs resources; retreat is reasonable |
   | deadly | 16×L | 60 | 1d10 | likely defeat without an edge |
   | mythic | 24×L | 65 | 1d10, +1 dmg per 5 margin | arc-level |

   The DM picks the tier from the fiction, fills the combat template, and
   **emits `threat: "<tier>"` on the NPC's character record** (an ordinary
   open entity attribute — no schema change) so the tier persists instead of
   being re-judged. Groups: several lower-tier foes over inflating one.

2. **Telegraph by default; surprise is earned and check-gated.** Foreshadow
   ≥1 turn ahead via the tension 4–6 complications — the pressure *is* the
   telegraph. A surprise encounter (ambush, betrayal, tension 9–10) always
   grants a **reaction check** (`mind` vs **the tier's Defense** — Russell
   ratified tier-Defense over a flat DC; it scales for free). Success = act
   normally; failure = the threat takes one free action. Never surprise AND
   a free action without the check — the player's dice are the player's.

3. **Every encounter offers ≥2 resolution paths** of fight / flee / parley /
   outwit. **Fleeing is a check, not a narration**: `body` or `mind` vs the
   tier's Defense; success = clean escape (tension −2); failure = escape
   **at cost** (a tier-die of damage, something dropped, or driven somewhere
   worse). Parley/outwit = `heart`/`mind` checks. A mythic threat may refuse
   parley; nothing refuses flee-at-cost. Pursuit/arrest = flee in reverse.

4. **Consequences persist.** On resolution the DM emits at least one durable
   change (hp, item, faction relation, a new tracked entity with its
   `threat` recorded, location danger, or a lingering condition a long rest
   clears). Plus the base block's tension drop. "An encounter that changes
   nothing didn't happen" — never an empty resolution.

5. **Non-combat kinds get one-line frames** (check → cost → consequence):
   trap (`mind` spot / `body` evade), illness (`body`; fail = −20 condition
   until a long rest or Cleanse), betrayal (`heart` reaction → parley/outwit
   or combat), weather/collapse (`body`; fail = damage + a lost time block;
   environment defaults to standard tier), pursuit (flee reversed). The kind
   stays a narrative choice; the frame it runs on is not.

## What landed

- **`engine/modules/tension/encounter-frames-v1/`** — manifest (`requires`
  four-stat + hp-pool + d100; time referenced, not required) + prompt (the
  tier table / telegraph + reaction check / paths + flee-at-cost /
  persistent consequences / non-combat frames).
- **`engine/modules/assembly.py`** — `DEFAULT_MODULES` += `"tension"`; the
  slot already existed in `CANONICAL_SUBSYSTEM_ORDER`, so no order change.
- **Tests** — `test_encounter_module_loads` (tier tokens, `threat: "<tier>"`,
  REACTION CHECK, AT COST, never-empty-resolution, don't-default-to-combat);
  default set → nine; assembly-order derivation includes the tension
  fragment; base integrity intact.

## Acceptance Criteria

- [x] `core/encounter-frames-v1` module: manifest + prompt (tiers / telegraph
      + reaction check / paths + flee-at-cost / persistent consequences /
      non-combat frames).
- [x] `DEFAULT_MODULES` grows to nine; assembly composes tension last; base
      fragment integrity intact.
- [x] Tests: module-loads + default-set + assembly-order updated.
- [x] RFC-0013 lands Implemented in the same PR.

## Out of Scope

- **A bestiary / monster catalog** — tiers are templates, not a creature
  list; named-creature content is preset/community-pack work.
- **Encounter *generation* tables** (random tables, biome lists) — the DM
  picks from fiction; data-driven generation is a later slice.
- **Multi-NPC initiative** — round-per-roll (RFC-0007) already abstracts it.
- **XP/loot tables** — progression is milestone-based (RFC-0009).
- **Schema enforcement of `threat`** — open attribute in v1, same posture as
  other module fields (RFC-0006 OQ1 lane).

## Cross-links

Base-v1 TENSION & ENCOUNTER PRESSURE (the *when* — untouched); RFC-0007
combat (the HP/Defense/damage math the tiers ground); RFC-0006 resolution
(all checks); RFC-0010 time+rest (conditions clear on long rest; weather
costs a block); RFC-0008 magic (Cleanse); the BACKLOG Core Systems
"Encounter mechanics" item; `project_fantasy_flagship_core_systems` memory.
