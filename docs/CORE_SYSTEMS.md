# Project Sentinel — Core Systems

> **Scope:** the canonical reference for Sentinel's **systemic layer** — the
> rules that attach mechanical meaning to the numbers the DM emits. This doc
> has two clearly separated halves per `CLAUDE.md`: a **Near-term** section
> (the shipped module set + the next committed slice) and a **Vision** section
> (the direction the systemic layer points, open questions allowed). For the
> architecture that packages these systems as swappable modules, see
> [ADR-0005](./adr/0005-subsystem-modularity.md); for what ships next across
> the whole project, see [`ROADMAP.md`](./ROADMAP.md).

_Last updated: 2026-07-02_

---

## Why this doc exists

Sentinel's ambient surfaces — the HP silhouette, the tension meter, entity
cards, encounter pressure — only mean something durable if the systemic layer
underneath is defined. A "50/100 HP wounded silhouette" is ambient feedback;
what 50 HP *does* (do rests heal it? potions? what does a killing blow commit
to?) is the systemic layer's job. When that layer is undefined, the DM invents
the answer turn-to-turn — fine for ambience, fragile for cohesion.

The flagship-genre approach (Russell, 2026-06-12): define the core systems for
**Fantasy** first as the canonical reference, then let other genres inherit the
same *shape* and swap only flavor (mana → energy cell → RAM → ritual; healing
potion → med-pack → bandage → spell). This collapses N independent rulesets
into **"1 template + per-genre overrides,"** which is how ADR-0005's module
architecture and the world-creation preset pipeline already want to work.

This file supersedes the "Core Systems — Fantasy as Flagship Model" section of
[`BACKLOG.md`](./BACKLOG.md) as the canonical home; the BACKLOG entry now points
here.

---

# Near-term

> What is committed: the shipped module set, and the single next slice.

## The nine-module default set (shipped)

Every slot in `engine/modules/assembly.py::CANONICAL_SUBSYSTEM_ORDER` is filled.
A vanilla Fantasy world runs `DEFAULT_MODULES`; the DM system prompt is assembled
from these fragments in canonical order.

| Subsystem | Module | RFC | What it commits |
|---|---|---|---|
| `base` | `core/base-v1` | [0005](./rfc/0005-module-infrastructure.md) | Status enum (`alive`/`unconscious`/`dead`/`unknown`/`missing`), the `<world_update>` frame, and the base DM behavior repackaged as a fragment. |
| `resolution` | `core/d100-open-v1` | [0006](./rfc/0006-resolution-and-character-sheet.md) | Real **client-rolled** d100 vs a DC — the roll is the trust anchor (real randomness, not LLM bias), the backend validates it (`RollResult`) and passes it through, and the DM resolves from the margin; it does not invent the number. |
| `character_sheet` | `core/four-stat-v1` | [0006](./rfc/0006-resolution-and-character-sheet.md) | Four-stat sheet (`body`/`mind`/`heart`/`will`) as schema fields under `module_data`. |
| `class` | `core/four-class-fantasy-v1` | [0007](./rfc/0007-class-and-combat.md) | Four Fantasy classes and their prompt-level flavor. |
| `combat` | `core/hp-pool-v1` | [0007](./rfc/0007-class-and-combat.md), [0014](./rfc/0014-death-stakes-enforcement.md) | HP pool as schema; the down-and-out ladder (0 HP → `unconscious` → death saves → `dead`). **The death ladder is now engine-enforced** (RFC-0014): death saves resolve through a tamper-proof, engine-authoritative path and `permadeath` is a real revival gate. |
| `magic` | `core/realm-pool-v1` | [0008](./rfc/0008-magic.md) | Realm-pool magic resource, spell effect tiers, Revive. |
| `progression` | `core/milestone-v1` | [0009](./rfc/0009-progression.md) | Milestone level-up. |
| `time` | `core/time-cycle-v1` | [0010](./rfc/0010-time-and-rest.md) | Day cycle + short/long rest recovery. Rest heals the living; it never revives the dead. |
| `tension` | `core/encounter-frames-v1` | [0013](./rfc/0013-encounter-mechanics.md) | Five level-scaled threat tiers, telegraph/surprise reaction checks, fight/flee/parley/outwit with flee-at-cost, persistent consequences, non-combat frames. Fills the reserved `tension` slot. |

## The enforcement gradient

The systems above sit at different points on a **narration → enforcement**
gradient, and that is the single most useful lens for what to build next:

- **Enforced** (the outcome follows from a real roll, DM dresses it):
  `resolution` — a real client-rolled d100, server-validated, resolved by the
  margin and surfaced to the player as a Roll affordance; and, as of RFC-0014,
  the **death save** — the engine computes the outcome from a server-recomputed
  margin and writes `status` + the death clock itself, so the DM cannot override
  a rolled death. The DM can't invent either result.
- **Prompt-honored** (DM is *asked* to follow the rule, nothing checks it):
  everything else.

RFC-0006 proved the enforced end is achievable without breaking the turn loop;
RFC-0014 took the highest-stakes rule — death — across the same line.

## Landed — death-stakes enforcement (RFC-0014, Option 2)

**The gap.** `engine/modules/combat/hp-pool-v1/prompt.md` instructs the DM to run a death save
(a `will` check vs Moderate 60; three failures → `dead`) and `base-v1` defines
the status enum, but all of it is DM-honored. The `permadeath` world flag is
**label-only** (`engine/types.py`, `engine/agents/dm.py`) — it appends a prompt
line and gates nothing. So the most consequential moment in the game — a
character dying — is exactly the moment the engine currently commits to least.
This is inconsistent with RFC-0006, where an ordinary check became a real,
server-validated roll instead of a DM-invented number.

**The decision (Option 2, approved 2026-07-02).** Move death saves onto the same
real-roll path as ordinary checks:

- The death save becomes a real `check_request` resolved through the **same
  client-rolled, server-validated `RollResult` flow** as every other check
  (`will` vs Moderate 60) — a real roll, not a number the DM invents. (It is
  *not* a new backend roll; that would fork a second dice model and break the
  player-visible Roll-affordance trust contract.)
- The three-strike death clock is **tracked in world/character state**, not held
  in the DM's context.
- Three tracked failures → the engine sets `status: dead`; healing/stabilize
  reverses the clock per the existing rules.
- `permadeath` becomes **load-bearing**: when set, `dead` refuses revival
  (Revive spell / healing on a dead character is rejected the way a schema-gate
  rejection is — fed back to the DM, not silently honored).

**Explicitly deferred to a later slice (was Option 3):** the world/session
*consequences* of a death — session end-state, an in-world memorial in
world-state, what a dead PC does to an in-flight world. RFC-0014 scopes the
enforcement mechanics; the consequence layer is its own follow-up.

Implemented in [RFC-0014](./rfc/0014-death-stakes-enforcement.md): the death
clock lives at `module_data.combat.death_saves_failed`; a `death_save`
`check_request` carries a `kind` field the frontend echoes back on `RollResult`;
the engine recomputes the margin server-side (so a forged client margin can't
dodge death) and injects the committed `status`/clock authoritatively; the
permadeath gate is a pure engine function run at dispatch-time that drops a
revival update and surfaces a rejection.

## Still open from the flagship list

With death-stakes landed, two named systems from the original flagship list
remain unbuilt — the next candidates:

- **Faction / economy basics.** No subsystem exists. Factions render as entity
  cards but carry no mechanical standing, reputation, or economy. A new
  `CANONICAL_SUBSYSTEM_ORDER` slot + module, additive per ADR-0005.
- **Weather / environment ambient rules.** RFC-0013 introduced a *weather
  encounter frame*; ambient (non-encounter) environmental effects — travel,
  visibility, exposure, resource drain — are still undefined.

---

# Vision

> Where the systemic layer points. Open questions allowed; nothing here is a
> commitment. Belongs in this half until it is concrete enough to become an RFC.

## 1 template + per-genre overrides

The end state is a **single Fantasy reference template** whose every system has
a defined structural role, and a set of **per-genre override modules** that swap
flavor while inheriting the structure. ADR-0005 already provides the seam: a pack
replaces just the subsystem it wants (just resolution, just magic) and inherits
the rest from core. The open design work is proving the override model on 2–3
genres (Sci-Fi + Cyberpunk are the obvious validators) so the "1 template + N
overrides" claim is demonstrated, not asserted.

## The enforcement question, generalized

Death-stakes is the first deliberate move of a prompt-honored rule to the
enforced end of the gradient. The open vision question is **how far that should
go**: which systems *benefit* from engine enforcement (stakes the player must
trust — death, resource ceilings, progression gates) versus which are *better
left narrated* (texture the DM should improvise — weather mood, faction
personality, flavor of a spell). Enforcing everything recreates a rules engine
and fights the "the world runs, you just play in it" thesis; enforcing nothing
is where we started. The gradient is the design surface, not a binary.

## Faction / economy as a systemic layer

Beyond "basics," the vision is factions with real standing that the world
simulates between a player's visits — reputation that decays, economies that
shift, alliances that form off-screen. This connects to the deferred
background-simulation direction in [`VISION.md`](./VISION.md) (APScheduler
ticking) and is explicitly *not* near-term.

## Minimum viable structure

The whole core-systems effort is one instance of Sentinel's standing research
question: **what is the minimum set of schema + rules that lets an autonomous
world stay coherent turn-over-turn without a human refereeing?** Each system
added is a wall; the goal is the fewest walls that still produce a world that
feels mechanically honest. Death-stakes is a high-value wall because the ambient
surfaces already imply it. The discipline is to add the next wall only when a
surface or a play session shows the gap — not to manufacture systems.

---

## How to use this document

When picking up core-systems work: read **Near-term**, take the committed next
slice if its prerequisites are met, and draft its RFC. When a system lands, move
it into the shipped table with its RFC link and promote the next gap. Vision
ideas graduate down into Near-term only when they are concrete enough to commit
to an RFC — never the reverse.

## References

- [ADR-0005 — subsystem modularity](./adr/0005-subsystem-modularity.md) — the
  module architecture these systems are packaged as.
- [`ROADMAP.md`](./ROADMAP.md) — project-wide near-term commitments.
- [`VISION.md`](./VISION.md) — the long-term direction and the core thesis.
- RFCs [0005](./rfc/0005-module-infrastructure.md)–[0013](./rfc/0013-encounter-mechanics.md)
  — the per-system designs that built the shipped set.
