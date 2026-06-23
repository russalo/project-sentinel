# ADR 0005 — Subsystem modularity (swappable roleplay-system modules)

**Status:** Accepted
**Date:** 2026-06-23
**Deciders:** Russell Pfister (ratified Option C, 2026-06-23 — "C for core, community can build the system how they like, they eventually need to be modules you can swap in and out"); Claude (design session 2026-06-23, prompted by the Fantasy-flagship core-systems work)
**Supersedes:** — (no prior ADR)
**Implementation:** Not started. First slice specced in RFC-0005 (module infrastructure foundation).

---

## Context

Sentinel is building a roleplay system: resolution mechanics, character sheets,
classes, magic, combat, progression, deity/patron binding, encounter pressure.
The Fantasy-flagship roleplay design (v0.1) takes a position on each of these as
a set of interlocking subsystems.

Two forces make a monolithic implementation wrong:

1. **Genres differ mechanically.** Fantasy magic (deity-bound divine realms,
   arcane traditions) is not sci-fi tech or cyberpunk netrunning. Combat,
   progression, and resolution may want different shapes per genre. The
   "1-template-plus-overrides" model (Russell's framing) means most mechanics
   are genre-agnostic, but some subsystems need genuinely different
   implementations per genre.

2. **Community must be able to build the system how they like** (Russell,
   2026-06-23). The long-term vision is that a community pack can replace any
   subsystem — ship a d100-open-ended resolution instead of d20, a
   skill-tree-freeform progression instead of milestone levels, an
   oath-and-corruption patron system instead of deity-binding — without
   rewriting the rest of the engine.

Today the DM's behavior lives in one hand-authored prompt monolith
(`engine/prompts/dm.py`); there is no structural seam where a subsystem's rules
can be swapped. Before any mechanics ship, the engine needs an architecture that
treats each subsystem as a replaceable unit.

This ADR commits to that architecture. It does **not** specify any subsystem's
mechanics — those live in the per-subsystem design docs + the modules
themselves. It specifies the **wiring** that lets modules plug in, coexist, and
be selected per-world.

## Decision drivers

- **Swappability.** Any subsystem's implementation must be replaceable by an
  alternate module sharing the same interface, without touching the others.
- **Per-world binding.** Different worlds run different module sets (a Fantasy
  world vs a sci-fi world; a vanilla world vs a community-modded world).
- **Community extensibility.** Community packs ship modules through the same
  filesystem + namespace-gate pattern that already governs community content
  (ADR-0001 + the fs-manager namespace gate).
- **LLM-DM constraints.** The DM is an LLM; its prompt must compose cleanly from
  module contributions, and state additions must stay namespaced + bounded so
  the model doesn't drift across an unbounded field space.
- **State truthfulness (ADR-0004, sibling track).** Module-added state lives in
  a namespaced container so the mutation-authority rules can reason about it.
- **Incrementality.** The architecture must land before mechanics, and the first
  slice must be provable with zero gameplay change (de-risk the structural shift
  before behavior rides on it).

## Options considered

### Option A — Monolithic, genre-flagged

One implementation; `if genre == "fantasy"` branches inside the engine + prompt.
Cheapest now. **Rejected:** every genre/community variation edits the core; no
seam for community replacement; the prompt monolith grows unbounded; exactly the
shape we're trying to escape.

### Option B — Per-genre forks

Each genre gets its own engine path. **Rejected:** N-independent-rulesets is the
anti-pattern Russell explicitly named; massive duplication; a community pack
can't target a single subsystem, only a whole genre fork.

### Option C — Subsystem modules with per-world binding (CHOSEN)

The roleplay engine is a registry of swappable per-subsystem modules. Core ships
one module per subsystem; community packs ship replacements. Each world binds a
set of modules at creation. The DM prompt is composed from the active modules'
contributions; module-added state is namespaced under `module_data.<subsystem>`.

This is the "1-template-plus-overrides" model made structural: the template is
the set of subsystem *interfaces*; the overrides are alternate *modules*
implementing those interfaces.

## Decision

**Adopt Option C.** Sentinel's roleplay engine is a registry of swappable
per-subsystem modules. The architecture commits to seven properties:

### 1. Subsystems are a fixed, extensible enumeration

The v0.1 subsystem set:

```
base            (invariant DM personality + STATE DISCIPLINE — always present)
resolution      (the dice/check mechanic)
character_sheet (stats / attributes)
class           (archetypes)
combat          (damage, HP, death)
magic           (casting mechanics / pool + caster bindings: deity/patron
                 for divine casters, tradition/school for arcane casters)
progression     (XP / level / milestone)
time            (turn shape — scene vs round)
tension         (encounter pressure)
```

Nine subsystems. `base` is a reserved pseudo-subsystem present in every world;
this list is the v0.1 floor, not a ceiling.

**Caster bindings (patron deities, arcane traditions) are internal concerns of
the `magic` subsystem, NOT peer subsystems** (decided 2026-06-23). They are
defined in terms of magic realms — a patron's domains gate which realms a divine
caster draws from; a tradition gates an arcane caster — so they cannot swap
independently of the magic module. A magic module owns its binding mechanics +
exposes binding content (deities, traditions) through its `preset_paths`, so a
community can add new deities/traditions as content without replacing the
module; replacing the binding *mechanics* (e.g. an oath-and-corruption system)
correctly entails replacing the magic module. The creation-time selectors
(PatronSelector / TraditionSelector) and the patron codex-entity are owned by
the active magic module.

### 2. A module is declared by a manifest

Each module ships a TOML manifest declaring: `name` (`<namespace>/<slug>-v<major>`),
`version`, `subsystem`, `interface_version`, `prompt_fragment` path,
`schema_fragment` path, `preset_paths`, and `requires` (module dependencies).
Core manifests live at `data/lore/core/modules/<slug>.toml`; community manifests
at `data/lore/community/<pack>/modules/<slug>.toml`.

### 3. Module-added state is namespaced under `module_data.<subsystem>`

No module writes flat top-level entity fields it owns. All module-contributed
fields live under `module_data.<subsystem>` on the entity. This lets an
alternate module replace a subsystem's state shape without colliding with the
base schema or other modules. The base entity fields (name, class, level,
attributes, status, currentLocation, role) are the shared contract every module
may read.

### 4. Each world binds a module set at creation, immutable for its lifetime

`data/state/core/world/state.json` carries a `modules: {<subsystem>: <module_slug>}`
map. It is selected at world creation (defaulting to the core set) and **frozen**
for the world's lifetime — swapping modules mid-game would break state
consistency. Worlds created before this field existed read a missing map as the
core default set (lazy default; no migration write).

### 5. The DM prompt is composed from module contributions

The DM prompt is assembled by walking the world's active modules in a canonical
subsystem order and concatenating each module's `prompt_fragment`. No subsystem's
rules are hard-coded in the engine; each module teaches the DM about its own
mechanics through its fragment.

### 6. Module loading reuses the core-vs-community namespace pattern

The module loader scans both `data/lore/core/modules/` and (when present)
`data/lore/community/<pack>/modules/`. Community modules load read-only through
the same path pattern; the existing fs-manager namespace gate (ADR-0001) governs
that community packs cannot *write* to `data/lore/core/`. Module loading itself
is read-only and identical for core + community.

### 7. Interface versioning gates compatibility

Each module declares `interface_version`. The engine implements a contract
version per subsystem; it loads a world only if every bound module's interface
version is compatible. Additive minor contract changes are backward-compatible;
breaking changes bump the major version and require modules to re-declare.

## Rationale

- **Option C is the only one that gives community a single-subsystem seam.** A
  pack can replace just the patron system, or just resolution, leaving everything
  else core. A + B both force whole-engine or whole-genre edits.
- **`module_data.<subsystem>` namespacing is what makes alternates coexistable.**
  Without it, two patron modules both wanting a "standing" field collide. With
  it, each owns its sub-object.
- **Per-world immutable binding** sidesteps the hardest problem (live module
  migration) by declaring it out of scope: a world is its module set. This is the
  same move ADR-0002 made with `world_id` — identity fixed at creation.
- **Prompt composition** turns the monolith into a set of focused fragments that
  evolve independently and version per-module — directly addresses the
  unbounded-prompt-growth failure mode.
- **Reusing the namespace gate** means modularity inherits ADR-0001's security
  model for free; community modules can't escalate to core writes.
- **The first slice ships zero gameplay change** (RFC-0005) — the architecture is
  proven by migrating today's behavior onto it before any mechanics depend on it.
  This is the lowest-risk way to land a structural shift this large.

## Consequences

**Positive:**
- Community can replace any subsystem without forking the engine.
- Genres pattern as content overrides (Layer 1) or module overrides (Layer 2) on
  a shared skeleton — no N-rulesets duplication.
- The DM prompt becomes a composition of focused, versioned fragments.
- Module-added state is bounded + namespaced, friendly to both LLM tracking and
  the ADR-0004 mutation-authority rules.
- New subsystems + new modules land as additive RFCs, each riding the same
  plumbing.

**Negative / costs:**
- Upfront architecture cost before any mechanics ship (RFC-0005 is pure
  plumbing).
- Indirection: reading the DM prompt now means assembling fragments, not reading
  one file. Mitigated by the canonical order + a "render the assembled prompt"
  debug path.
- Per-module test burden: each module should prove it satisfies its subsystem
  contract.
- Interface-versioning discipline: contract changes must be versioned carefully
  to avoid breaking saved worlds.

**Neutral / deferred:**
- Mid-game module swapping is unsupported (a world is its module set). A future
  ADR could spec migration paths between compatible versions.
- A module marketplace / discovery / distribution layer is out of scope; modules
  ship by filesystem placement.
- Cross-language module SDK is out of scope; modules are Python + TOML + Markdown.

## Implementation implications

Sequenced as RFCs under this ADR (each rides the prior):

- **RFC-0005 — Module infrastructure foundation.** Manifest format + loader +
  `world.modules` field + `module_data` namespacing + module-composed prompt
  assembly. Ships `core/base-v1` (today's DM behavior, repackaged). Zero gameplay
  change; equivalence-tested.
- **RFC-0006 — Resolution + character-sheet modules** (`core/d20-vs-dc-v1`,
  `core/four-stat-v1`).
- **RFC-0007 — Class + combat modules** (`core/four-class-fantasy-v1`,
  `core/hp-pool-v1`).
- **RFC-0008 — Magic module** (`core/realm-pool-v1`) — including its internal
  caster bindings (deity/patron for divine, tradition/school for arcane) +
  their content + selectors.
- **RFC-0009 — Progression module** (`core/milestone-v1`).

Touch points: `engine/modules/` (new package), `engine/prompts/dm.py` (becomes
the assembly + base shim), `backend/routes/session.py::new_session` (defaults
`world.modules`), the character-entity schema (gains `module_data`),
`engine/agents/dm.py` (threads modules to prompt build), `engine/README.md`
(documents the architecture).

Relationship to ADR-0004 (state truthfulness): orthogonal + complementary.
ADR-0004 governs *what* may mutate state (player/system/DM authority lines);
ADR-0005 governs *how* the rules-of-mutation are packaged + swapped. ADR-0004's
boundaries become enforceable once mechanic modules (RFC-0006+) define real
fields under `module_data.<subsystem>`.

## Open questions (to resolve during RFC-0005 implementation)

These are wiring-level, not architecture-level — the decision above stands
regardless of how they resolve:

1. **Prompt-fragment storage** — `.md` files (recommended) vs Python constants.
2. **Canonical subsystem order** for assembly — ship the full v0.1 list now
   (recommended) vs grow per-RFC.
3. **Character-entity schema location** — confirm where the stored entity (vs the
   update payload) is validated; `module_data` may need a new/different schema.
4. **Per-module contract enforcement** — Pydantic models per subsystem; land with
   each subsystem's RFC, not RFC-0005.
5. **Saved-world version migration** — additive minor versions auto-upgrade;
   major versions require migration (spec in a later RFC).

## References

- [RFC 0005 — Module infrastructure foundation](../rfc/0005-module-infrastructure.md)
  — the first implementation slice (manifest, loader, registry, prompt
  assembly, `core/base-v1`)
- The Fantasy-flagship roleplay design (v0.1) — the mechanics this architecture
  serves. A working design doc, not yet ratified into a committed spec; lives
  in the session's scratch notes until its mechanics settle.
- ADR-0001 (canonical state on disk) — the file layout + namespace gate modules
  reuse
- ADR-0002 (world identity & isolation) — `world.modules` lives on the per-world
  state established there; the "identity fixed at creation" pattern is mirrored
- ADR-0003 (access gating) — orthogonal; module loading is read-only
- ADR-0004 (state truthfulness — proposed) — sibling track; governs mutation
  authority over the state these modules define
- Russell's direction, 2026-06-23: "C for core, community can build the system
  how they like, they eventually need to be modules you can swap in and out"
