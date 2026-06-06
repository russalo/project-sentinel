# Canon / Modules — Research Findings (2026-06-06)

> **Status:** Research artifact captured during the 2026-06-06 design conversation
> with Russell. **Not a plan**; not a decision document. Grounds the
> [Canon/Modules conceptual model](../README.md) in what already exists on disk
> vs. what would have to be built, so a future session doesn't have to re-derive.
>
> **Conceptual companion:** `~/.claude/projects/-srv-projects-project-sentinel/memory/project_canon_modules_framing.md`
> (the conceptual model — Modules = the 6 baseline datasets per genre; Canon =
> seed-authored + emergent-via-History; 2-vector chatlog harvest;
> History-as-link-table).
>
> **When this becomes hot:** post-cutover, when the closed alpha generates
> real corpus + the smoke harness exists. Until then this informs Entity Sweeper
> design + future doc work.

## TL;DR

**Canon/Modules is the architectural concept that retires ~10 BACKLOG items
if landed well.** Most of the "schemas are too loose / DM fabricates / player
mints from prose" failure-mode items collapse into "we defined Canon and
Modules properly." The infrastructure to support it (namespace gate,
override hierarchy, protected fields, per-world isolation, preset framing
layer) is already further along than expected — but the actual *Module
schemas* and *Canon content* are mostly missing. This isn't a
green-field design problem; it's a "formalize what's been implicit, fill in
gaps that are documented but not built" problem.

---

## What's already in place

| Concept | Where | State |
|---|---|---|
| **Core/Community namespace gate** | `ARCHITECTURE.md` §1–§4 + fs-manager enforcement | ✅ Live. `?namespace=core` trusted query param (red-team #7 fix); community writes blocked from core paths; protected fields enforced via `x-sentinel-protected` extension keyword. |
| **Override hierarchy** | `ARCHITECTURE.md` §2 | ✅ Documented: Core State > Core Lore > Community State > Community Lore. The Canon-vs-emergent decision line is *already* the philosophical line in this doc. |
| **Protected fields catalog** | `ARCHITECTURE.md` §4 | ✅ Six fields: `unique_id`, `world_seed`, `namespace`, `created_at`, `canon`, `core_faction_id`. But ⚠️ — see gap below. |
| **Per-genre framing layer (Layer 1 of Modules' precursor)** | `data/lore/core/presets/` — 5 genres × {3 personas, 6 moods, 5 regions} = 34 TOML files | ✅ PR #39 shipped. Fantasy has its `prompt_fragment` + 4 regions (Crown City, The Breach, The Wastes, Thornwatch). |
| **Preset → DM intro composition** | `backend/presets.py` + `engine/agents/dm.py::_build_intro_messages` + `backend/routes/session.py:120-138` | ✅ Live. Player picks genre/persona/mood/region → backend resolves TOML fragments → injected as "WORLD FOUNDATIONS" block. |
| **Per-world isolation infrastructure** | ADR 0002 Slices 1–5 + Path A | ✅ Built, dormant. When `SENTINEL_WORLDS_ROOT` flips, each world gets its own `data/` tree. Canon-per-world and History-per-world land **automatically** if we put them under `data/`. |
| **DM state-discipline rules** | `engine/prompts/dm.py` — "STATE DISCIPLINE" section | ✅ Partial: "Entity singularity" rule + "No invented history" rule already injected. These ARE Canon-enforcement rules in prompt form — just informal. |
| **Per-session log + per-turn structured shape** | `data/state/core/sessions/<uuid>.json` | ✅ Each session has `turns[]` with `id, turn_number, player_action, narrative, world_updates, created_at`. Different shape from History-as-link-table — these are per-DM-output records, not relational event records. |
| **Architectural scaffolding** | Scanner's `scratch/scanner_sentinel_parallels.md` (cross-linked) + `project_canon_modules_framing` memo | ✅ The promotion-machinery isomorphism gives us the design template for Vector-2 harvest when the work lands. |

## Critical gaps

| Gap | Where it bites | Existing BACKLOG item |
|---|---|---|
| **Entity schemas are PERMISSIVE.** `apply_world_update.schema.json` requires only `session_id`/`log_entry`/`updates`. Entity-level shape is open. Sample on disk: each `entities/*.json` has ad-hoc fields the DM chose. | No formal Module shape; lots of "schemas are too loose" failure modes | Multiple — enum-chaos, free-text class, modifiers-as-string-concat, lazy-fabrication, etc. |
| **`unique_id` / `world_seed` / `created_at` aren't actually set on existing entities.** They're listed as protected in `ARCHITECTURE.md` but on-disk JSONs key on filename slugs. | Vector-1 promotion needs stable refs; History-as-link-table needs FK targets | BACKLOG: "World identity, world_seed persistence, and multi-session semantics" |
| **`data/lore/core/codex/` is EMPTY.** The "Trog in Sunken Citadel" example in `ARCHITECTURE.md` §2 is hypothetical — no actual canonical lore files exist. | Lorekeeper has nothing to query (VISION acknowledges this gates Lorekeeper from being actionable) | BACKLOG: Lorekeeper agent + ChromaDB indexing (gated on lore content) |
| **`world/state.json` is minimal.** Currently just `{tension, currentLocation, weather, timeOfDay}`. No `genesis` block, no `world_seed`, no canon pointers. | World genesis can't be persisted; resume can't restore Day N | BACKLOG: World identity (genesis proposal exists, not built) |
| **No History dataset.** Per-turn data exists in session logs but not as a relational link-table. | The "Sir Reginald can't show up alive next session" enforcement has no canonical record to check against | **NEW** — not yet on BACKLOG |
| **No Vector-1 promotion machinery.** Entity Sweeper is design-stage. | Implicit narrative entities (cloak, brother, cult) stay lost | BACKLOG: Entity Sweeper |
| **No Vector-2 promotion machinery.** Schema induction doesn't exist. | Can't grow new Module types from accumulated chatlog | **NEW** — not yet on BACKLOG |
| **WorldCreation Layer 2 unwired.** Player picks genre/persona/mood/region; only the prompt-fragments compose. Entity seed-data from the region (e.g. Crown City's "Four Houses" mentioned canonically in the TOML) doesn't get materialized as `data/state/.../*.json` entries — the DM has to re-invent them every session. | Canon promised in the TOML isn't enforced on world-gen | BACKLOG: "WorldCreation presets are unwired and undefined" |

## What this concept retires from BACKLOG (if landed well)

This is the single most important operational observation. The following
BACKLOG items collapse into "Canon/Modules is properly defined":

- *Over-eager reference resolution* → Canon defines what *can* exist
- *Lazy fabrication on extraction* → History records make facts immutable
- *Player-authored entity gate* → Canon-vs-emergent boundary IS the gate
- *Schema enum chaos* → formal Module schemas (Item.schema, NPC.schema, etc.)
- *Class compatibility validation* → Module catalog of valid classes per genre
- *Modifiers as string concat* → formal modifier fields per Module
- *WorldCreation Layer 2 unwired* → Modules ARE the wiring
- *Entity Sweeper undefined* → Vector-1 harvest IS the sweeper
- *Lorekeeper has no lore* → Canon populates `data/lore/core/codex/` for Fantasy
- *World genesis not persisted* → `world/state.json` gets a `canon_seed` pointer

That's not coincidence — these items are *symptoms* of the architectural
concept being implicit rather than formal.

## Real operational constraints

1. **No code path in `apply_world_update.schema.json` exists today for History entries.** Adding a Module-aware schema (with referential validation: `actors[]` ids must exist) is genuinely new schema engineering.
2. **The Fact-Extractor is a regex parser** — `engine/agents/fact_extractor.py:320 lines, _BLOCK_PATTERN = re.compile(r"<world_update>...</world_update>")`. It can only see what the DM emits. Either (a) the DM has to emit `<history_entry>` explicitly, or (b) Entity Sweeper (LLM-driven, second-pass) does it.
3. **The smoke harness doesn't exist** (BACKLOG: "Repeatable smoke test harness — scripted player inputs, deterministic seed, captured transcripts"). The minimum-viable-structure loop in VISION needs it as the prerequisite for *measuring* whether Canon/Modules actually improves coherence. **Without the harness, Canon/Modules design becomes faith-based.** This is also blocked on the paid Groq tier (free-tier TPM 429s on any sustained run).
4. **`data/lore/core/codex/` being empty is a content authoring problem, not a code problem.** Fantasy's canon (pantheon, pre-game history) is genuinely missing content; someone has to write it. Russell or a curation pass.
5. **Per-world isolation must be flipped on before History becomes meaningful** — otherwise History from world A bleeds into world B (the BACKLOG "session boundary isn't world boundary" failure mode). Not a Canon/Modules problem per se, but a prerequisite cutover.
6. **The closed alpha is the data-generation event.** The chatlog corpus needed to drive Vector-2 promotion doesn't exist yet — until real testers play, there's nothing to induce schemas from.

## Phased trajectory (NOT a plan — discussion starter)

**Phase 0 — Prerequisites (must land before any of this becomes evidence-based):**
- Cutover (`SENTINEL_WORLDS_ROOT` flip) so worlds are actually isolated
- Smoke harness (BACKLOG) so coherence becomes measurable
- Paid Groq tier so the harness can actually run
- Closed alpha plays so chatlog corpus exists

**Phase 1 — Seed Canon for Fantasy (mostly content, some structure):**
- Define Fantasy seed Canon content: pantheon TOMLs, pre-game history TOMLs, established-faction TOMLs under `data/lore/core/codex/fantasy/`
- Schema-formalize the existing implicit entity shapes (NPC, Item, Faction, Location) — bring on the protected fields that `ARCHITECTURE.md` already promises
- Wire WorldCreation Layer 2 — region presets materialize their canonical entities at world-gen
- One ADR captures: "Modules = the 6 baseline datasets per genre, schema-formal; Canon = seed lore + History; History per-world graph hub"

**Phase 2 — History module (the connective tissue):**
- New `History` Module: schema + dispatch + relational refs
- Decision: which write-shape (DM `<history_entry>` / Fact-Extractor derivation / Sweeper-driven). Probably hybrid (b)+(c).
- Other modules gain optional relational fields that point at History entries

**Phase 3 — Vector-1 promotion (Entity Sweeper):**
- The cloak/brother/cult promotion — `mentioned_only: true` → tracked
- Already designed in `project_entity_sweeper_direction`; the parallels doc is the scaffolding
- Lands as a real engine agent

**Phase 4 — Vector-2 promotion (schema induction):**
- Far-future. Needs corpus volume (months of alpha minimum).
- Uses Scanner's candidate→provisional→stable ladder + Wayne-K rule analogue
- Promotes new Module *types* from observed chatlog patterns
- Probably never auto-promotes Canon — Canon stays curated

## Open questions for the next iteration

1. Is "Fantasy flagship" meant to include authoring the Canon content (Phase 1) as part of this, or push that to a separate content-authoring pass after the structure is built?
2. The History write-shape decision (DM block / Fact-Extractor / Sweeper) — instinct already, or land empirically via the smoke harness?
3. The `unique_id` / `world_seed` / `created_at` schema-enforcement gap — file as a Phase 1 prereq?
4. Should Vector-2 promotion (new Module types from observed chatlog) be on BACKLOG now, or wait until Phase 1-3 land?

## Cross-links

- `project_canon_modules_framing` memory — the conceptual model
- `project_entity_sweeper_direction` memory — Vector-1 design history
- `project_minimum_viable_structure_loop` memory — Russell's vision frame
- `/srv/projects/pkplab/scanner/scratch/scanner_sentinel_parallels.md` — Scanner's promotion-machinery isomorphism (2026-04-11; load-bearing scaffolding)
- `docs/VISION.md` § "The minimum-viable-structure research loop" + § "Lorekeeper + ChromaDB RAG"
- `docs/BACKLOG.md` § "World Generation" + the long list of symptom-items above
- `ARCHITECTURE.md` §1–§4 (the Core/Community framework that's already half this design)
