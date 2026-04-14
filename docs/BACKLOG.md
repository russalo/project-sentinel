# Project Sentinel — Backlog

Items that need to be addressed but were not part of current planning or implementation.
Agents: append discovered items under the appropriate section using the format below.
Completed items should be removed by the end-session workflow, not left to accumulate.

---

## Format

```
- [ ] Short description of the item
      _Discovered: YYYY-MM-DD | Context: brief note on where/why this surfaced_
```

---

## Architecture Decision Records

Decisions of this scope that have been committed to the repo live under `docs/adr/`.
Items in this backlog may reference an ADR for context.

- **ADR 0001** — `data/` is canonical source of truth (Accepted 2026-04-13). Drives the High Priority items below.

---

## High Priority — Do Soon

The Inference Node work is unblocked by ADR 0001. The order below reflects
the dependency chain: each item needs the previous one landed to be
implementable.

- [ ] **New FastAPI backend to replace Django.** Replaces `backend/sentinel/` + `backend/api/` with a FastAPI application. Reads directly from `data/` (no ORM, no Django models in the hot path). Calls the engine for turn handling. Dispatches writes through `engine.dispatch` to `fs-manager`. Preserves the existing SSE response contract (`{type: 'token', content}`, `{type: 'world_update', data}`, `[DONE]`) so the frontend continues working without changes. Sized at ~500–800 lines of Python + tests. Matches the async model and dependency stack used by the MCP servers.
      _Discovered: 2026-04-13 | Context: ADR 0001 Phase 1 core deliverable; retires PR #7's Django backend after it has served its purpose (unblocking the frontend and proving the SSE flow)_

- [ ] **Retire `artifacts/api-server/` (Express dev reference) and `lib/db/` (Drizzle schema).** These have been double-dead-code since PR #7 and retire together with the Django backend they referenced. Removes their workspace members from `pnpm-workspace.yaml` and updates `tsconfig.json` / root `package.json` accordingly. Removes `just dev-backend` from the `justfile`.
      _Discovered: 2026-04-13 | Context: ADR 0001 implementation implications_

- [ ] **Delete `world-engine/` entirely.** The three prompt YAMLs (`dm.yaml`, `fact-extractor.yaml`, `lorekeeper.yaml`) may be useful reference when writing the engine's agent prompts, so keep them until the engine agents are implemented — then remove the directory. Also remove `world-engine` from `scripts/check-structure.sh` at the same time.
      _Discovered: 2026-04-13 | Context: world-engine/ was retained during the engine/ scaffold PR to avoid deleting reference material prematurely; still retained until the new DM agent has harvested anything reusable from the YAMLs_

---

## Phase 2 — Deferred

These items depend on Phase 1 being stable. They are not prerequisites
for v1.0 and should not be worked in parallel with Phase 1.

- [ ] **Drop Postgres entirely from the Docker stack.** ADR 0001 Phase 2. Remove `sentinel-postgres` from `infrastructure/docker-compose.yml`, delete `infrastructure/migrations/*.sql`, remove any remaining psycopg2 references and DATABASE_URL wiring, update `just` recipes and health checks accordingly. Phase 1 already ships without any Postgres consumer — `backend/` reads from `data/` directly and never queries the database — so Phase 2 is purely cleanup.
      _Discovered: 2026-04-13 | Context: ADR 0001 Phase 2; Phase 1 now confirms the cache layer was never built, so Phase 2 is uncontested — just needs scheduling_

- [ ] **Rewrite `README.md` and `ARCHITECTURE.md` Core Loop narratives to match running code.** The forward-pointing callouts added in PR #10 (ADR 0001) were placeholders until the code caught up. Phase 1 has now shipped; the callouts can be replaced with accurate descriptions of the running system. `ARCHITECTURE.md` §7 (Full Update Pipeline) should describe the engine → fs-manager → git-sync path as the actual per-turn flow, and the Node Roles table (§5) should describe the FastAPI backend and retired Django.
      _Discovered: 2026-04-13 | Context: ADR 0001 said "rewrite after Phase 1 ships"; Phase 1 has now shipped_

- [ ] **Revisit the `db-vector` MCP server's role.** Currently designed as "route structured queries to Postgres, semantic queries to ChromaDB." Under ADR 0001 Phase 2, Postgres goes away, so `db-vector` becomes either a ChromaDB-only wrapper or a unified read layer over `data/` + ChromaDB. Decide what it is during Phase 2.
      _Discovered: 2026-04-13 | Context: ADR 0001 Consequences § Neutral — flagged as requiring a design decision during Phase 2_

- [ ] **Lorekeeper agent + ChromaDB indexing.** Once the core loop is running end-to-end under the new backend, add the RAG step. Index `data/lore/**/*.md` into ChromaDB on startup and on filesystem change (either a file watcher or a restart-only indexer). The Lorekeeper agent queries ChromaDB for context and injects results into the next DM turn. `engine/agents/lorekeeper.py` doesn't exist yet — scaffold + implementation are both part of this item.
      _Discovered: 2026-04-13 | Context: ADR 0001 mentions this as "later" — not a Phase 1 concern, but the natural next step after the core engine loop is running_

- [ ] **Background simulation / world progression.** The "world keeps evolving while you sleep" piece from the README tagline. Cron-driven agent runs that mutate `data/` via the same engine → fs-manager path as player turns. Needs a locking story so simulation writes don't collide with player turns (file-level lock via fs-manager, or sequencing via a queue). Not Phase 1.
      _Discovered: 2026-04-13 | Context: referenced in ARCHITECTURE.md §7 (orchestrator/simulation); currently not scaffolded; Phase 2 or later_

---

## Architecture & Structure

- [ ] **Auth strategy decision (future):** two clear paths remaining — (1) simple API key middleware for single-player public deployment, (2) outsourced JWT (Auth0/Clerk/Supabase) if password management is unwanted. SSE streaming endpoint has no conflict with either — auth middleware runs before the stream opens. Decision not needed for 1.0. The Django User model path is no longer on the table now that Django has retired.
      _Discovered: 2026-03-27 | Updated: 2026-04-13 | Context: originally Django-era planning; trimmed to viable FastAPI-era options only_

---

## Documentation Drift

- [ ] **`docs/WORKSPACE.md` is stale — rewrite against the current stack.** The document still lists "API framework: Express 5" and describes `artifacts/api-server/src/lib/dm-ai.ts` as the AI architecture — neither file nor framework exists any more. Rewrite against the current reality: FastAPI backend reading `data/state/*.json`, engine package as the Inference Node, the retired Django/Express/Drizzle history collapsed to a one-line "previously" note. Should happen together with the `README.md` / `ARCHITECTURE.md` rewrite tracked under Phase 2 above.
      _Discovered: 2026-04-13 | Updated: 2026-04-13 | Context: Phase 1 has shipped; no longer gated, just scheduling_

- [ ] **`CHANGELOG.md` `[Unreleased]` section is empty of ~6 months of work.** No entries for PR #7 (Django backend + SSE), PR #5 (frontend clean build), Replit migration, `just`/chezmoi tooling, PR #9 (Lane A housekeeping + engine scaffold), or anything since. Either catch it up in one pass from git history and resume maintenance, or add a note at the top that the changelog is currently unmaintained so contributors aren't misled.
      _Discovered: 2026-04-13 | Context: surveyed during the engine/ scaffold PR doc audit; pre-existing drift, not touched in that PR_

---

## Engine Package

- [ ] **Entity Sweeper — second-pass extraction agent for implicit narrative entities.** The DM writes evocative prose that implies entities, relationships, places, and items without always formally declaring them in the `<world_update>` block — a cloak described on the player character, a "brother" name-dropped by an NPC, a cult alluded to, a temple mentioned in passing. Those implicit things become meaningful the moment a player might act on them. Right now they're lost to the Fact-Extractor because it only captures what the DM emits as explicit state. The design direction (captured in memory, discovered during the 2026-04-14 smoke test): add a new `engine/agents/entity_sweeper.py` agent that runs after the Fact-Extractor on the same raw DM response, identifies entities mentioned in the narrative but absent from the structured state, and emits supplementary upserts merged into the final fs-manager dispatch. Planned schema addition: optional `mentioned_only: bool` field so the frontend can render latent entities differently (grayed out / hidden in a separate section) until the player explicitly interacts with them. Key design decisions still open: cost model (second LLM call per turn — route to a smaller model via LiteLLM? run async in background? skip on short narratives?), duplicate avoidance (sweeper sees current world state in its prompt context), and whether to cover all of characters/locations/factions/items from day one. **Before implementation, write an ADR** capturing the above; smaller than ADR 0001 but the same shape.
      _Discovered: 2026-04-14 | Context: surfaced when the user noticed the intro narrative described their Shadowmancer's cloak but the inventory panel was empty. User explicitly rejected the ad-hoc prompt-bullet approach ("add a line to DM_SYSTEM_PROMPT telling it to emit starting gear"). This is a proper new engine capability, not a prompt tweak._

- [ ] **`engine/schema.py` schema-path coupling.** `_SCHEMA_PATH` is hard-coded to `Path(__file__).parent.parent / "schemas" / ...`, which only resolves correctly when `engine/` sits at the repo root alongside `schemas/`. The PR #9 boundary contract states `engine/` should be extractable into a standalone package; in that scenario this path breaks. Fix options: (a) bundle the schema as package data and load via `importlib.resources`, (b) copy `schemas/` into `engine/` as a sibling of `engine/schema.py`, or (c) have the caller inject the loaded schema or its path. Option (c) is the cleanest architecturally but changes `validate()`'s public API. Defer until extraction actually happens.
      _Discovered: 2026-04-13 | Context: flagged by Copilot on PR #9; documented in the module docstring of engine/schema.py and deferred to this item instead of reworked in the scaffold PR_

---

## World Generation

- [ ] **WorldCreation presets are unwired and undefined — need real content + a generation pipeline that uses them.** The WorldCreation form today collects six decisions from the player (World Name, Character, Class, Genre, Tone, Starting Region, DM Persona, Mood, Modifiers like Sandbox/Permadeath) but the `handleBegin` handler in `apps/sentinel-ui/src/pages/WorldCreation.jsx` only ships three fields to `POST /api/session/new`: `worldName`, `playerCharacterName`, `playerCharacterClass`. Every other preset the player selected is silently dropped on the floor. That's a lie in the UI: the player thinks they're shaping their world by picking "Horror + Gritty + The Breach + Oracle," but the backend gets none of it, so the DM generates whatever it would have generated for any fantasy world.

  Fixing this is a two-layer problem, both of which have to land for it to mean anything:

  **Layer 1 — Wire the fields.** `NewSessionRequest` (backend/schemas.py) gains `genre`, `tone`, `starting_region`, `persona_id`, `mood`, and the modifiers. The frontend stops dropping them. The backend can then at least feed them as free-form context into the intro prompt so the DM has *something* to anchor to.

  **Layer 2 — Define what each preset contains, and how the generation process uses it.** This is the real design work. Each preset needs both a definition and a pipeline entry:

  - **Genre definitions** (e.g. Fantasy, Sci-fi, Western, Horror, Cyberpunk) — what themes, tones, tropes, vocabulary, and "forbidden moves" does each imply? Content lives under `data/lore/core/presets/genres/<genre>.md` (human-readable, contributor-authorable) and/or `data/state/core/presets/genres/<genre>.json` (structured metadata: key tropes, color palette for UI, DM tone shifts).
  - **Starting region definitions** (The Breach, Thornwatch, Crown City, The Wastes) — each region is essentially a seed. It should define: a starting location, a set of initial NPCs or factions, an opening hook, geography and connected regions. When the player picks one, the backend injects that seed into the intro generation so the DM is producing *this specific region's* opening, not a generic one.
  - **DM persona definitions** (Oracle, The Chronicler, etc.) — each persona is a voice, a tone, a narrative style. Persona selection should meaningfully alter the system prompt the DM runs with (e.g. "You are the Oracle — prophetic, detached, fragmentary" vs. "You are the Chronicler — historian, precise, reverent"). Persona definitions live under `data/lore/core/presets/personas/<persona>.md` + a JSON metadata file with compatible genres and moods.
  - **Mood modifiers** (Neutral, Gritty, Lore-heavy) — these stack on top of persona. A "Gritty Oracle" is different from a "Neutral Oracle." Probably the cheapest layer: a set of prompt fragments appended to the base system prompt.
  - **World modifiers** (Sandbox Mode, Permadeath) — these affect backend behavior too, not just the DM prompt. Sandbox unlocks persona changes mid-game; Permadeath prevents resurrection in state mutations. These need engine-level enforcement, not just DM prompt hints.

  **The generation pipeline at session-create time:**
  1. Player submits WorldCreation form with all their preset selections
  2. Backend loads the matching preset definition files from `data/lore/core/presets/` (and/or content-addressed overrides from community packs)
  3. Backend assembles an intro prompt that merges: DM_SYSTEM_PROMPT base + selected persona prompt + selected mood modifier + genre tropes + starting region seed
  4. Backend calls `engine.agents.dm.generate_intro` with the merged prompt
  5. DM generates the intro → Fact-Extractor produces apply_world_update payload → fs-manager dispatches
  6. Starting region's seed entities (from the region definition) are merged into or supplement the DM's output — so "The Breach" always has certain canonical NPCs present, even if the DM forgot

  **New `engine/agents/` piece likely:** `world_seed.py` (or similar) — a small helper that composes the merged prompt from preset content, similar to how `fact_extractor.py` composes the apply_world_update payload. Not necessarily a second LLM call — more of a prompt-assembly utility.

  **Content needed (substantial):** every preset above needs written content — the Markdown definitions, the JSON metadata files, and the seed entities for each region. This is real worldbuilding work, probably a Lore-Smith contributor pathway activity rather than an engineer task.

  **Order of operations when this becomes work:**
  1. Start with just Layer 1 (wire the fields end-to-end, pass everything as free-form context) — one PR, immediate UX improvement
  2. Then define the preset file layout (maybe an ADR — how do presets live under `data/`? how do they compose with community packs?)
  3. Then author a minimum viable set of preset content (probably one entry per category to prove the pattern)
  4. Then build the generation pipeline that consumes it
  5. Finally expand preset coverage to the full form
      _Discovered: 2026-04-14 | Context: user observed during smoke test that the WorldCreation form asks a lot of questions but none of them actually shape the generated world — the DM's intro is identical regardless of what you pick for tone, genre, region, etc. First issue filed under a fresh "World Generation" BACKLOG section because this area is clearly going to accumulate more items_

---

## DM Personas & Content Framework

The "the world grows, but within frameworks" principle is already
documented in `ARCHITECTURE.md` §1 (Core/Community namespace separation)
and §3 (Community Gateway via `community.json`). The framework exists
on paper — lore, entities, factions, and schemas are all supposed to
live under `data/{lore,state}/{core,community}/` with protected fields
and override hierarchies. But the DM personas, action catalogs, and
world-generation presets being discussed throughout this backlog
aren't yet plugged into that framework at all. The items below are
about finishing the wiring so community contributors can extend the
world without reinventing anything.

- [ ] **DM personas as framework content, not hardcoded behavior.** Today there's a single `DM_SYSTEM_PROMPT` in `engine/prompts/dm.py` and the WorldCreation form shows personas ("Oracle", "The Chronicler") as options, but picking a persona has zero effect on the running DM — there's no code path that loads a persona definition and applies it to the prompt. Personas need to be authored content that plugs into a defined framework:

  **Persona layout under `data/lore/core/presets/personas/<persona_id>/`:**
  - `persona.md` — human-readable description (voice, tone, narrative style, what makes it distinct). This is what a Lore-Smith authors.
  - `persona.json` — structured metadata: `{id, name, compatible_genres, compatible_moods, description_summary}`. This is what the WorldCreation form reads to populate the PersonaSelector. Also includes framework version so older personas break loudly rather than silently on upgrade.
  - `system_prompt.md` — the DM system prompt addendum or override. Can be a full replacement for `DM_SYSTEM_PROMPT` or (more likely) a fragment that gets composed in.
  - `voice_rules.md` — optional, deeper stylistic constraints ("Oracle speaks in fragments", "Chronicler always dates events").

  **Composition model:** there's a base DM contract (the part every persona must honor — emit `<world_update>`, tag agents correctly, respect the schema gate, end with choices) and a persona layer (voice, tone, themes, emphasis). At session-create time, the backend loads the selected persona's files and composes a final system prompt = base DM contract + persona system_prompt + persona voice_rules + any mood/genre modifiers. This is similar to the World Generation pipeline item above — probably the same pipeline, since persona + genre + mood are all preset dimensions of the same intro composition.

  **Community extensibility:** contributors drop a new persona directory under `data/lore/community/<author>/personas/<persona_id>/` with the same file shape. The persona registers itself via the community pack's `community.json` manifest (already defined in `schemas/community_manifest.schema.json`). The engine walks community personas on startup the same way it walks core personas, and the WorldCreation form shows both — with the namespace separator respected (core personas can't be overridden, community personas are always lower RAG priority, etc., per ARCHITECTURE.md §2).

  **Framework guarantees:** the framework defines what a persona MUST provide and what it MAY override. Core fields (the base DM contract — schema gate behavior, `<world_update>` emission rules, agent tagging) are immutable from any persona override. Persona layer fields (tone, voice, choice framing) are fully overridable. This is the same "protected fields" pattern from ARCHITECTURE.md §4, applied to prompt composition instead of entity state.

  **Relation to other items:**
  - **World Generation (this BACKLOG)** — persona selection is one of the preset dimensions the generation pipeline composes. Same pipeline reads genre + region + persona + mood and merges them all.
  - **Player Actions & Game Mechanics (this BACKLOG)** — a persona might declare which action sets it expects to work with (e.g. Oracle is bad at combat mechanics, Chronicler is good at social intrigue). Personas can constrain or suggest action-set selection during world creation, not mandate it.
  - **ARCHITECTURE.md §3 Community Gateway** — the `community.json` schema already exists but doesn't yet list `personas` as a declarable pack content type. That schema needs an extension to add `personas`, `action_sets`, `genres`, `regions`, and the rest as valid pack contributions alongside the existing `locations`/`npcs`/`items`/`factions`.

  **Generalization of the principle:** every extensible content type in Sentinel should follow the same shape:
  1. A core framework contract (what the content type guarantees)
  2. A file layout under `data/lore/core/presets/<type>/` (and the community mirror under `data/lore/community/<author>/<type>/`)
  3. A JSON metadata file that the engine reads to register and validate
  4. A markdown file for human-readable description / authored content
  5. A composition pipeline in the engine that loads and applies it
  6. An entry in `community.json` for community pack declaration

  Applying this to: DM personas, action catalogs (base + advanced), genre definitions, region seeds, mood modifiers, world modifiers, and future additions. When this is built, adding a new "Horror + Gritty + The Oracle + Desert Wastes" world is purely a content authoring job — zero code changes required.

  **Order of operations when this becomes work:**
  1. Write an ADR capturing the persona (and general preset) framework: file layout, composition model, what's core-protected vs overridable, how `community.json` extends, how the engine loads and validates presets
  2. Migrate the existing `DM_SYSTEM_PROMPT` in `engine/prompts/dm.py` into the framework — the current single prompt becomes one persona entry ("default" or "Oracle") under `data/lore/core/presets/personas/`, with the base contract extracted separately
  3. Add preset loading to the backend — probably `engine/presets.py` (or similar) that walks the preset tree at session-create time and exposes a composition API
  4. Extend `schemas/community_manifest.schema.json` to declare `personas`, `action_sets`, `genres`, `regions` as declarable pack content types
  5. Wire the WorldCreation form to actually use the selected persona (once the frontend fields are wired per World Generation item above)
  6. Author a second persona (probably The Chronicler) as the proof-of-concept "second persona" to validate the composition pipeline actually produces different DM behavior
  7. Document the contributor pathway in `CONTRIBUTING.md` — "how to author a new DM persona" as a Lore-Smith activity
      _Discovered: 2026-04-14 | Context: user said "And DMs too. We want the world to grow, but based on existing frameworks." — reaffirming that the DM persona system should plug into the Core/Community framework documented in ARCHITECTURE.md §§1–3, not be hardcoded as it currently is_

---

## Player Actions & Game Mechanics

Right now, the player can type literally any verb and the DM improvises
around it. There's no action catalog, no validation that an action is
possible in the current context, no capability gating on character class
or traits, and no mechanical resolution for things like combat or magic.
The DM is holding the entire "what can you do" concept in its prompt
context, which is fragile and prevents any genre from having real rules.

- [ ] **Player action catalog — base set + advanced sets tied to genre/class/world.** Introduce an explicit action vocabulary that lives in content, not in the DM's head. The structure should have two tiers:

  **Base action set** (always available, genre-agnostic): `look`, `examine`, `wait`, `rest`, `move`, `talk`, `give`, `take`, `drop`, `use`, `search`, `attack`, `flee`, etc. These are the verbs every persistent-world game supports. Each base action has a definition with fields like `name`, `aliases` (the words a player might type to mean it), `requirements` (what must be true to perform it — e.g. `move` requires a known exit from the current location; `give` requires the player to possess the item being given), `narrative_cues` (how the DM should frame the outcome), and mechanical effects (what state changes).

  **Advanced action sets** (opt-in per world, loaded based on genre and character capabilities):
  - **Combat system** — `parry`, `dodge`, `flank`, `aim`, `reload`, `cover`. Combat sets are pluggable so Fantasy combat, Cyberpunk firefights, and Western gunfights can each have their own.
  - **Magic system** — `cast`, `channel`, `counterspell`, `drain`, `summon`. Magic sets are keyed off character class: a Shadowmancer gets shadow-magic verbs, a Ranger gets none.
  - **Social** — `persuade`, `intimidate`, `deceive`, `appraise`. Probably universal but tone shifts per genre.
  - **Crafting / survival** — `craft`, `forage`, `tend_wound`, `light_fire`. Genre-specific (a hard-sci-fi game has no crafting; a wilderness survival game has a lot).

  **Content layout:** actions live alongside world-generation presets under `data/lore/core/presets/actions/`. Probably one file per action group: `base.yaml`, `combat/fantasy.yaml`, `combat/cyberpunk.yaml`, `magic/shadow.yaml`, etc. A world's genre + persona + character class determines which files load.

  **The validation / classification pipeline:** when the player types "I parry the shadowbeast's lunge", the backend needs to:
  1. Match the input against available actions via alias lookup or fuzzy match (LLM-assisted if necessary, rule-based first-pass for performance)
  2. Check the matched action's `requirements` against current state — can the player parry? does the character have a weapon? is there something to parry?
  3. If valid, pass to the DM with structured context: "Player chose action=parry, target=shadowbeast, applicable mechanics=fantasy_combat"
  4. If invalid, reject with an explanation surfaced as a system message — "You can't parry without a weapon. You currently have: nothing equipped." — and let the player try again

  The DM prompt then knows what action was chosen AND what mechanics apply, instead of having to guess from prose.

  **Relation to existing items:**
  - **Suggested actions (Turn UX #2)** — the frontend can build the "click to type" suggestion pills directly from the currently-available action catalog, not just from DM prose. Cleaner source of truth.
  - **World generation presets (World Generation section)** — an action-set selection is a preset dimension. "Fantasy + Combat + Magic(shadow)" is three preset files merged.
  - **Entity Sweeper (Engine Package)** — the Sweeper can notice when the DM describes an implicit-action moment ("you could try to pick the lock") and surface it as an advanced action that gets added to the session's available set. Not a hard coupling; just a path.

  **Design decisions deferred until this becomes real work:**
  - Resolution model for actions with mechanical consequences: deterministic rules vs. dice rolls vs. LLM-judged. Probably genre-specific (a narrative horror game has no dice; a dungeon crawler has d20).
  - Where dice / probability lives: engine-side (pure Python), frontend-side (visible to player), or LLM-side (described in prose).
  - How the Permadeath modifier from WorldCreation enforces itself — permadeath means the engine refuses mutations that would resurrect a dead character, which requires action gating + state-layer enforcement.
  - Whether the base action set is actually fixed, or also pluggable (some worlds might not have combat at all).

  **Order of operations when this becomes work:**
  1. Define the action file format (YAML/JSON schema) and write the base set — one PR, all content, no code
  2. Add action catalog loading to the backend — `engine/actions.py` or similar, reads from `data/lore/core/presets/actions/` at session-create time, attaches to the session
  3. Pass the active action catalog into the DM prompt so the DM knows the verbs it's working with
  4. Wire input classification — simplest form first (alias lookup + hard rules), LLM fallback later
  5. Author advanced sets per genre and wire them via the world generation preset pipeline
  6. Add mechanical resolution for at least one genre (fantasy combat most likely) as a proof of concept
      _Discovered: 2026-04-14 | Context: user observed during smoke test that they could type any action and the DM would improvise — "Right now I could make up any action and it would have to try to make it work"_

---

## Frontend / Turn UX

Turn-finalization UX surfaced as a clear gap during the 2026-04-14 smoke
test: the FastAPI backend correctly streams tokens, updates state files
through fs-manager, and ships a `world_update` SSE event — but the frontend
does nothing to help the player *see* what changed or *act* on what's
next. The panels silently reflect new state; there's no "moment" in each
turn that says "here's what matters right now." These three items
together are what turn the raw narrative output into playable game UI,
and they should probably ship as one or two coordinated PRs because they
all touch the frontend's turn-finalization code path and the DM prompt
at the same time.

- [ ] **Turn-delta feedback (cheap, pure frontend).** After each turn, compute the diff between the previous world state and the new `world_update` SSE payload and render it as a styled system message at the end of the turn, or animate affected panels with a pulse + before/after indicator. Example output: "Tension: 9 → 10. The Shadowbeast appeared. Russalo: wounded (100 → 85)." **Zero backend work, zero extra LLM calls** — the data to compute the diff is already in chatStore / worldStore. ~1 day of React/Zustand work. Biggest immediate UX win; ship this first.
      _Discovered: 2026-04-14 | Context: user observed during smoke test that state was changing but nothing made it visible to the player — "there needs to be interface or system feedback on the turn when the DM responds, the part of the world update that is relevant to the player"_

- [ ] **Suggested actions as structured field (hybrid: prompt + schema + frontend).** The DM already writes these in prose at the end of every turn ("Do you strike with shadow magic, let Thalia's arrow find its mark, or use the key?") — they should be a structured array in the `<world_update>` block, not buried in narrative. Proposed schema addition: `suggestedActions: [{"label": "...", "tone": "aggressive|defensive|clever|..."}]`. Frontend renders as clickable pills under the command bar; clicking types the label into the input (does NOT auto-submit — player still reviews). Frontend supplements with rule-based "always-available" actions ("Look around", "Rest", "Wait"). Tiny schema addition + small bullet in `DM_SYSTEM_PROMPT` + small frontend component. No extra LLM call — the DM emits in its existing response. Graceful fallback when the DM forgets: show the rule-based standards only.
      _Discovered: 2026-04-14 | Context: the DM always ends turns with choice-prompts but they're buried in prose; surfacing them as UI commits the player to a cleaner interaction model_

- [ ] **Exits / navigation (schema addition + frontend).** Exits belong as a property of the Location entity, not as a top-level world field. Extend the location schema with `exits: [{"direction": "north", "destination": "Hollowed Temple"}]`. Frontend renders a compass / directions panel tied to the player's current location; clicking an exit types e.g. "I head north toward the Hollowed Temple" into the command bar. DM prompt bullet asks it to populate exits whenever introducing a new location. Additive schema change, no extra LLM call. Same DM-forgets fallback story as suggested actions. Lower urgency than #1 and #2 — only matters when movement is a gameplay axis, which it isn't yet.
      _Discovered: 2026-04-14 | Context: paired with suggested actions — together they give the player explicit verbs and explicit nouns to work with_

**Relation to the Entity Sweeper item in "Engine Package":** Items #2 and #3 here (suggested actions, exits) are things the DM mentions in prose but doesn't always emit as state — the same pattern as the cloak case that motivated the Entity Sweeper. The Sweeper's second-pass extraction model could generate these as a fallback when the DM forgets. Item #1 (turn-delta feedback) is orthogonal — pure frontend derivation, no extraction needed.

---

## Developer Experience

- [ ] Add unit and integration tests for `apps/sentinel-ui/` — Zustand stores, API client, and key components
      _Discovered: 2026-03-26 | Context: flagged in PR #5 review; no tests exist for any of the 8 frontend phases; recommend vitest + @testing-library/react_

- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
