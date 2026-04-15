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

## Where we are

ADR 0001 Phases 1 and 2 are both fully landed. The Inference Node (engine
package) is wired into a FastAPI backend that reads state directly from
`data/state/*.json` and dispatches every write through the complete
engine → fs-manager → git-sync path. Django, Postgres, the orphaned
`db-vector` MCP server, and the legacy `world-engine/` scaffolding are
all gone. The per-turn git audit trail is real and verified end-to-end
against a live LLM.

For what ships next vs. the long-term vision, see `docs/ROADMAP.md` and
`docs/VISION.md`. This BACKLOG tracks everything *discovered* that
doesn't yet belong in the roadmap.

---

## Deferred (post-Phase-2)

These items were called out as future work in ADR 0001 but are not yet
scheduled. They stay here until they earn a spot on `docs/ROADMAP.md`.

- [ ] **Lorekeeper agent + ChromaDB indexing.** Add the RAG step to the turn loop. Index `data/lore/**/*.md` into ChromaDB on startup and on filesystem change (either a file watcher or a restart-only indexer). The Lorekeeper agent queries ChromaDB for context and injects results into the next DM turn. `engine/agents/lorekeeper.py` doesn't exist yet — scaffold + implementation are both part of this item.
      _Discovered: 2026-04-13 | Context: ADR 0001 mentions this as "later" — the natural next step after the core engine loop is running under the new backend_

- [ ] **Background simulation / world progression.** The "world keeps evolving while you sleep" piece from the README tagline. Cron-driven agent runs that mutate `data/` via the same engine → fs-manager path as player turns. Needs a locking story so simulation writes don't collide with player turns (file-level lock via fs-manager, or sequencing via a queue).
      _Discovered: 2026-04-13 | Context: referenced in ARCHITECTURE.md §7 (orchestrator/simulation); currently not scaffolded_

---

## Architecture & Structure

- [ ] **Auth strategy decision (future):** two clear paths remaining — (1) simple API key middleware for single-player public deployment, (2) outsourced JWT (Auth0/Clerk/Supabase) if password management is unwanted. SSE streaming endpoint has no conflict with either — auth middleware runs before the stream opens. Decision not needed for 1.0. The Django User model path is no longer on the table now that Django has retired.
      _Discovered: 2026-03-27 | Updated: 2026-04-13 | Context: originally Django-era planning; trimmed to viable FastAPI-era options only_

---

## Documentation Drift

- [ ] **`docs/WORKSPACE.md` is stale — rewrite against the current stack.** The document still lists "API framework: Express 5" and describes `artifacts/api-server/src/lib/dm-ai.ts` as the AI architecture — neither file nor framework exists any more. Rewrite against the current reality: FastAPI backend reading `data/state/*.json`, engine package as the Inference Node, the retired Django/Express/Drizzle/Postgres history collapsed to a one-line "previously" note. The README/ARCHITECTURE rewrite in the cleanup PR didn't touch this file.
      _Discovered: 2026-04-13 | Updated: 2026-04-14 | Context: drift not addressed in the README+ARCHITECTURE rewrite; lower priority than those were because WORKSPACE.md has fewer readers_

---

## Engine Package

- [ ] **Entity Sweeper — second-pass extraction agent for implicit narrative entities.** The DM writes evocative prose that implies entities, relationships, places, and items without always formally declaring them in the `<world_update>` block — a cloak described on the player character, a "brother" name-dropped by an NPC, a cult alluded to, a temple mentioned in passing. Those implicit things become meaningful the moment a player might act on them. Right now they're lost to the Fact-Extractor because it only captures what the DM emits as explicit state. The design direction (captured in memory, discovered during the 2026-04-14 smoke test): add a new `engine/agents/entity_sweeper.py` agent that runs after the Fact-Extractor on the same raw DM response, identifies entities mentioned in the narrative but absent from the structured state, and emits supplementary upserts merged into the final fs-manager dispatch. Planned schema addition: optional `mentioned_only: bool` field so the frontend can render latent entities differently (grayed out / hidden in a separate section) until the player explicitly interacts with them. Key design decisions still open: cost model (second LLM call per turn — route to a smaller model via LiteLLM? run async in background? skip on short narratives?), duplicate avoidance (sweeper sees current world state in its prompt context), and whether to cover all of characters/locations/factions/items from day one. **Before implementation, write an ADR** capturing the above; smaller than ADR 0001 but the same shape.
      _Discovered: 2026-04-14 | Context: surfaced when the user noticed the intro narrative described their Shadowmancer's cloak but the inventory panel was empty. User explicitly rejected the ad-hoc prompt-bullet approach ("add a line to DM_SYSTEM_PROMPT telling it to emit starting gear"). This is a proper new engine capability, not a prompt tweak._

- [ ] **`engine/schema.py` schema-path coupling.** `_SCHEMA_PATH` is hard-coded to `Path(__file__).parent.parent / "schemas" / ...`, which only resolves correctly when `engine/` sits at the repo root alongside `schemas/`. The PR #9 boundary contract states `engine/` should be extractable into a standalone package; in that scenario this path breaks. Fix options: (a) bundle the schema as package data and load via `importlib.resources`, (b) copy `schemas/` into `engine/` as a sibling of `engine/schema.py`, or (c) have the caller inject the loaded schema or its path. Option (c) is the cleanest architecturally but changes `validate()`'s public API. Defer until extraction actually happens.
      _Discovered: 2026-04-13 | Context: flagged by Copilot on PR #9; documented in the module docstring of engine/schema.py and deferred to this item instead of reworked in the scaffold PR_

---

## World Identity & Multi-Session

Surfaced during the 2026-04-14 engine → git-sync wiring PR
(commit 56c70ee landed the first real per-turn commit from the
live backend). The question *"the git-sync is per world seed &
session? How do we track?"* exposed three interlocking gaps in
how world identity is modeled today. None of them are bugs in
the smoke test — they're unanswered design questions that
Phase 1 didn't need to resolve but any further world-content
work will.

- [ ] **World identity, world_seed persistence, and multi-session semantics.** Three related gaps, all of which should be settled together in one ADR (smaller scope than 0001 but same shape), because any partial answer creates more confusion than no answer.

  **Gap 1 — `world_seed` is dropped on the floor.** The WorldCreation form collects it, `NewSessionRequest.world_seed` passes it to `engine.IntroInput`, `engine.agents.dm.generate_intro()` injects it into the DM's user message as the `seed_context`, and that's the end of its life. Nothing persists it to disk. When the backend restarts or a new session is created in the same data/ tree, the seed is gone and unrecoverable. The `<world_update>` hint the DM emits never contains it either, so the Fact-Extractor never has a chance to write it. The backend explicitly silently loses this user input on every turn.

  **Gap 2 — no world-level identifier.** Every session under `data/state/core/sessions/<uuid>.json` shares the same `data/state/core/entities/`, `locations/`, `factions/`, `items/`, and `world/state.json`. There is no concept in the backend of "which world am I in" — the `read_session`/`write_session` helpers in `backend/state/sessions.py` look up by session UUID and return the session, but the *world* the session belongs to is implicit in which data/ tree the backend is pointed at. Creating a second session in the same data/ tree would silently inherit all the entities from the first session's world (Russalo, Thalia, Garek, the Hollowed Temple) — which is fine if the intent is "multi-session within one world" (resume a campaign, branch a what-if playthrough from an earlier point, run one character's story alongside another's in the same setting), but there's no code path that expresses or enforces that intent. The backend has no way to say "start a fresh world, wipe entities" without a contributor manually `rm -rf`ing the data tree.

  **Gap 3 — no `world_id` in git-sync commit messages.** The current format is `[sentinel] session=<id[:8]> turn=<N> — <summary>` with the full session UUID in the commit body. You can filter one playthrough with `git log --grep "session=<id>"`. But if there are ever multiple worlds coexisting in the same data/ tree, or if a deployment ever wants to multiplex worlds (separate clones? branches? subdirectories?), there's no world-level tag in the commit history to disambiguate them — you'd have to chain session-to-world via a separate lookup. And if a user imports a `.spak` from another world into the same repo clone, commit history would be silently inconsistent with the world identity it's supposed to represent.

  **Intended model** (based on re-reading README, ARCHITECTURE.md, and the Sentinel Porter language in `ARCHITECTURE.md §8`): **one `data/` tree = one world**. Multiple worlds live as separate `data/` trees — probably separate clones, possibly `.spak` imports of packaged worlds, possibly separate git branches in the same clone. A single world has many sessions across its lifetime (you play today, save, come back tomorrow, continue; or you start a second character's playthrough in the same setting). Entities persist across sessions within a world. They don't leak across worlds, because worlds don't share a data/ tree.

  **Under that model, the minimum wiring to fix all three gaps:**

  1. **Add a world genesis record to `data/state/core/world/state.json`**. Currently that file holds live world state (currentLocation, tension, weather, time). Extend its schema with an optional `genesis` block that captures world identity on first write and never changes thereafter:
     ```json
     {
       "genesis": {
         "world_id": "<uuid4>",
         "world_seed": "<the seed_context the player provided>",
         "world_name": "...",
         "created_at": "<iso timestamp>",
         "presets": {
           "genre": "...", "tone": "...", "starting_region": "...",
           "persona_id": "...", "mood": "...", "modifiers": [...]
         }
       },
       "currentLocation": "...",
       "tension": 5,
       "weather": "...",
       "timeOfDay": "..."
     }
     ```
     The `genesis` block is set once by session/new on world creation, and every subsequent update to `world/state.json` preserves it (either via merge semantics in fs-manager's `update` operation, or via an explicit protected-field list analogous to `unique_id`/`created_at`/`canon` in ARCHITECTURE.md §4).

  2. **Persist the world_seed during session creation.** `backend/routes/session.py` should, after the DM intro dispatch succeeds, emit a second apply_world_update payload that writes the `genesis` block to `world/state.json`. Or — simpler — teach the DM prompt to always emit a `genesis` block in the `<world_update>` on session-start turns (and nowhere else, ever). The Fact-Extractor then handles it uniformly.

  3. **Thread `world_id` through git-sync commits.** The engine `commit_snapshot` dispatcher gains an optional `world_id` parameter; the commit message format becomes `[sentinel] world=<world_id[:8]> session=<session_id[:8]> turn=<N> — <summary>`; git-sync's `/tools/commit_snapshot` endpoint accepts the new field. This is the smallest change — additive, no breakage of existing commits.

  4. **Session reads should include world context.** `backend/state/sessions.py::read_session` already returns a Session dataclass; extend `load_world_context` in `backend/state/world_context.py` to also surface the genesis block so the DM prompt can reference "you are in a world created with the seed X, genre Y, starting region Z" on every turn, not just session-start. This is how you get genre-aware DM behavior that actually persists across turns.

  **Unresolved design questions** that the ADR should settle:

  - **Multi-world-per-instance.** Is the intended deployment model strictly one-world-per-clone, or do we want a single backend process to multiplex multiple worlds (with a selector in the WorldCreation URL)? If multiplexed: how does the data/ layout change? Do we namespace everything under `data/worlds/<world_id>/…`? If so, every path reference in the engine / backend / MCP servers needs updating.
  - **Sessions as branches vs. linear history.** Right now all sessions in a world commit to the same branch; their commits interleave in timestamp order. Is that right, or should each session be its own branch so you can swap between playthroughs? git-sync today has no branch awareness.
  - **`.spak` import target.** When a `.spak` is imported, does it create a new clone, or can it be merged into an existing data/? If merged, what are the conflict semantics (protected fields, world_id uniqueness)?
  - **Resume vs. new session in same world.** The frontend currently only has "begin a new world" — there's no "resume existing session" or "start a new character in the same world" UX. That's a frontend question tied to backlog items in the Frontend/Turn UX section, but it affects what the world identity model needs to support.
  - **Multi-player future.** None of the above considers multi-player. If two players share a world, session_id ≠ player_id and the schema gains another layer. Deferred, but the world identity work should not actively preclude it.

  **Why log as one item, not three.** Splitting them produces half-answers (persisting world_seed without a world_id to tag it against, or tagging commits without a world genesis to tag *with*, etc.). All three need to land together or the model stays inconsistent.

  **Before implementation, write an ADR.** It should cover: the one-world-per-clone decision (or a decision to support multiplexing), the `genesis` block schema, the commit message format change, and the frontend UX for resume/new-session-in-world. Probably 200–400 lines, roughly half the length of ADR 0001.
      _Discovered: 2026-04-14 | Context: user asked "the git-sync is per world seed & session? How do we track?" during the engine → git-sync wiring PR, when they saw commits tagged with session_id in the git log. The honest answer is: per-session only, world_seed isn't persisted anywhere, and multi-session-same-world vs multi-world-per-instance isn't decided — it's all implicit today. This item captures the design gap before any of the World Generation / Player Actions / DM Personas Framework items try to build on top of "what does a world mean."_

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
  1. ✅ Layer 1 (wire all fields end-to-end, pass as free-form context) — fully landed. PR #20 wired initial fields; PR #33 completed Layer 1.5 (persona resolved to name + description) and wired genre/tone/startingRegion/mood/sandbox/permadeath through the frontend → backend → engine chain.
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

Turn-finalization and in-turn exploration UX both surfaced as clear
gaps during the 2026-04-14 smoke test. The FastAPI backend correctly
streams tokens, updates state files through fs-manager, commits via
git-sync (as of PR #14), and ships a `world_update` SSE event — but
the frontend does nothing to help the player *see* what changed,
*act* on what's next, or *read* about anything on screen. The panels
silently reflect new state with no way to inspect individual entries;
the chat shows only the narrative stream with no historical audit
view; there's no moment in each turn that says "here's what matters
right now." These items together are what turn the raw narrative
output into playable game UI. They should ship as one or two
coordinated PRs because they all touch the frontend's
turn-finalization code path and share the same visual primitives.

- [ ] **Panel UX system — unified state rendering across four views.** The session UI has four distinct views onto the same session state, each answering a different temporal question. This item designs them together because they share data sources, visual primitives, and user flows — splitting them produces divergent renderers for the same data and inconsistent visual languages for "this is what you should look at."

  **The four views and what each answers:**

  1. **Panel cards — "what is this right now?"** ✅ **Landed in PR #32.** `EntityCard` primitive built. Left-panel click handlers wired. Right-panel tabs (Codex, Inventory) live and wired to worldStore. Entity detail view in PanelRouter resolves live entity from worldStore (not a stale snapshot). Items collection added to worldStore.

  2. **Narrative scroll — "what is the DM saying right now?"** Existing, mostly works. `NarrativeScroll.jsx` + `DMMessage.jsx` handle the DM stream with a typewriter cursor. No changes required except making the chat area *tabbed* (see view 3).

  3. **System log tab — "what has happened across the whole session?"** ✅ **Phase 1 landed in PR #34.** `Narrative | System Log` tabs built. chatStore gains `systemLog[]`. `DeltaMessage` component in both inline (narrative) and log modes. Unread badge on System Log tab. Phase 2 (backend hydration across reloads) and Phase 3 (git-history-backed) remain open.

     Source of truth options:
     - **Frontend-only (Phase 1):** chatStore gains a `systemLog: []` array that accumulates delta messages as they arrive via the `world_update` SSE event. Lost on page reload.
     - **Backend-backed (Phase 2):** new `GET /api/session/<session_id>` endpoint returns the full session with `turns[]`, each turn containing its `world_updates` hint block. Frontend hydrates the system log from that on session load. Survives reloads.
     - **git-history-backed (Phase 3 / far future):** since git-sync now produces per-turn commits (PR #14), a new `GET /api/session/<id>/history` endpoint could read git log filtered by session_id and expose the commit history directly. Makes "view world at turn N" possible via `git show`. Overkill for v1.0.

  4. **Turn-delta feedback — "what just happened at the end of this turn?"** ✅ **Core landed in PR #34.** Inline `DeltaMessage` after each turn in the Narrative scroll. Pending: animated pulse on affected panel cards + EntityCard `diff` mode (before/after highlights on click-to-inspect). Those are lower priority — the textual delta is the primary signal.

  **Shared primitives — build once, consume everywhere:**

  - `EntityCard` + `PropertyList` — schema-driven entity renderer (per `docs/FRONTEND_PLAN.md §4` and §6). Takes any entity dict and produces a styled card. Two modes: `current` (full state display, used by click-to-read) and `diff` (before/after highlights, used by turn-delta feedback when the entity changed). Pure component, no store wiring — all views consume it with data passed as props. Unit-testable against fixtures without mounting the app.
  - `DeltaMessage` — renders a single "what changed" event as a styled system message. Used by the turn-delta feedback (rendered inline in the narrative scroll) AND by the System Log tab (each log entry is a DeltaMessage instance). Same visual language in both places.
  - `TabbedChat` — small wrapper around `NarrativeScroll` that adds tab switching between Narrative and System Log. Could be shared with a future ThirdTab if needed.

  **Data sources and flow:**

  - **Current state** flows: SSE `world_update` event → `worldStore.applyUpdate(hint)` → panel cards (view 1) re-render.
  - **Narrative** flows: SSE `token` events → `chatStore.appendToBuffer` → NarrativeScroll re-renders, then `[DONE]` → `chatStore.commitStreamMessage` → permanent message in scroll.
  - **Turn-delta** flows: when `world_update` arrives, compare against previous snapshot in worldStore → compute delta → emit a DeltaMessage to chatStore's `systemLog` (view 3 persistent) AND emit a transient styled system message in the narrative scroll (view 4 ephemeral) AND trigger pulse animations on affected panel cards (view 1 indicator).
  - **Historical log** flows: on page load or session resume, hydrate `chatStore.systemLog` from either in-memory accumulation (Phase 1) or a new GET /api/session/<id> endpoint (Phase 2).

  **Build ordering:**

  1. Build the shared primitives — `EntityCard`, `PropertyList`, `DeltaMessage` — as pure components with fixture-based tests. No store wiring yet. These are the smallest unit that unblocks everything else.
  2. Wire the right-panel tabs (Codex, Inventory, QuestLog) to `worldStore` using `EntityCard` in `current` mode. This kills the hardcoded empty-state lie immediately.
  3. Add click-to-expand on the left-panel list items — same primitive, opens in a right-panel drawer. Hovering the Characters/Locations/Factions lists already suggests clickability; this makes the suggestion real.
  4. Implement turn-delta computation in `chatStore` — diff incoming world_update vs previous worldStore snapshot, produce a list of delta events. Emit them as styled system messages in the narrative scroll for the ephemeral feedback.
  5. Add the TabbedChat container and wire the System Log tab to the same delta event stream — persistent historical view. Phase 1 is frontend-only accumulation; Phase 2 hydrates from a new backend endpoint.
  6. Add pulse animation on affected panel cards. On click of a pulsing card, open the detail card in `diff` mode instead of `current` mode. Unifies the "see what changed" and "read the full detail" flows.
  7. Optional Phase 3: new `GET /api/session/<id>` backend endpoint reads the session file and returns it as JSON. Frontend hydrates systemLog from that on page load. Makes the feature durable across reloads.

  **Open UX questions the joint design needs to answer:**

  - **Card open during new turn** — if a player has Russalo's detail card open in the right-panel drawer and a new turn arrives that modifies Russalo, does the card live-update with a visible diff, stay static until dismissed, or flash a "new data" indicator? Leaning: live-update in diff mode with a subtle "turn N+1 just landed" marker at the top of the card. Player sees the change without losing their place.
  - **Right-panel drawer vs inline expand vs modal** — where does the detail live? Right-panel drawer (replaces Codex/Inv/Quest tabs temporarily) uses existing real estate and doesn't interrupt the narrative. Inline expand (accordion-style in the left panel) is more discoverable but cramps the left-panel layout. Modal interrupts the chat. Leaning: right-panel drawer with a "close" action that returns to the last-selected tab.
  - **System Log tab notification** — when the player is on the Narrative tab and a new delta arrives, does the System Log tab get a badge (unread count), a subtle pulse, a highlight, or nothing? Leaning: badge with unread count, cleared when the player switches to the tab.
  - **Removed entities** — does clicking a character that was removed in a prior turn show a tombstone card with "last seen: turn N, status: dead"? Or do they vanish from the list entirely? Tombstones are more interesting but require `worldStore` to track removed entities in a separate collection instead of deleting them. Leaning: tombstones — they're the game's memory, not an error state.
  - **Empty states vs "never discovered"** — if the Codex tab is wired to worldStore and worldStore has one character, the panel shows one character. If worldStore is empty, what's the empty state? Is it the same "No discoveries yet" text as before, or something that distinguishes "fresh session, nothing yet" from "turn 1 happened but the DM didn't emit anything"?
  - **Per-turn evolution timeline in the card** — does the detail card show ONLY current state, or also a timeline of how this entity evolved across turns (via git history lookup)? Phase 2+ territory, but the shape matters because it affects whether `EntityCard` needs a third mode (`timeline`) beyond current/diff.
  - **System Log tab scroll anchoring** — when new entries arrive, does the tab auto-scroll to newest (like a chat) or preserve the user's scroll position (like a log)? Leaning: preserve scroll position if the user has scrolled up, auto-scroll if they're at the bottom.
  - **Keyboard navigation** — arrow keys to navigate between panel cards? Number keys to jump to tabs? Deferred to implementation.

  **What the other Turn UX items are NOT.** Suggested Actions (#2) and Exits (#3) are INPUT mechanisms — they surface what the player can DO next. This Panel UX system is DISPLAY mechanisms — it surfaces what IS, what CHANGED, and what HAPPENED. Both compose (a pulsing entity card in view 4 draws the player's eye to a target, suggested-action pills in another area offer verbs that apply to it), but the two concerns are separable and can ship independently. This item is only about the four display views.

  **Relation to other BACKLOG items:**

  - **Entity Sweeper (Engine Package).** When implemented, the Sweeper produces entities with `mentioned_only: true`. `EntityCard` needs a visual state for those — grayed out, italicized, or tagged "glimpsed" until the player interacts. The primitive should accommodate this mode from day one even if the Sweeper ships later.
  - **World Identity & Multi-Session.** If the world identity model introduces a world_id into every commit and entity record, the System Log tab's backend endpoint should filter by world_id not just session_id. Cross-reference on implementation.
  - **Suggested Actions (Frontend / Turn UX #2).** Compose as input-vs-display. Don't block each other, but the turn-delta visual ("pulse the affected entity") and the suggested-actions visual ("here are your pills") should feel like one coherent end-of-turn moment.
  - **Exits (Frontend / Turn UX #3).** Same — the compass panel and the location card share the Location entity schema, so `EntityCard` on a location dict should probably surface the exits array prominently.
  - **git-sync audit trail (ADR 0001 Phase 1, done in PR #14).** The System Log tab is a natural UI on top of the audit trail that git-sync now produces. Phase 3 of this item reads git log directly; git-sync's commit messages already contain session_id and turn metadata, so the wiring is mostly a new backend endpoint away.

  **Before implementation: ADR — DEFERRED until Entity Sweeper + system log work begins.** Originally filed as a prerequisite ADR that would pin down drawer-vs-modal, the Phase 1/2/3 system-log source split, removed-entity tombstone behavior, and composition with the Entity Sweeper's `mentioned_only` state. On 2026-04-15 that framing was revisited: all four of those open questions depend on downstream work (Entity Sweeper, system log) that doesn't exist yet, so writing the ADR before those items are real would be premature. The initial Panel UX primitives (`EntityCard`, click-to-inspect wiring, panel tabs) are therefore being built directly on `feat/panel-ux-entity-cards` without a preceding ADR — small enough to prototype, and the ADR-level questions don't block the primitives work. The ADR itself is deferred to whenever Entity Sweeper or system log work begins, at which point its open questions have enough context to be answerable.
      _Discovered: 2026-04-14 | Context: user asked during the smoke test whether they could read details on the panel cards (no — they're name-only lists with a decorative hover effect, plus the right-panel tabs are hardcoded empty-state text). That revealed the display surface is a coupled system: panel detail reading, turn-delta feedback, and a new System Log tab for historical audit are really four views on the same underlying data and have to be designed jointly. Replaces the previous "Turn-delta feedback (cheap, pure frontend)" backlog entry, which was too narrow — it framed turn feedback as a standalone ephemeral feature without accounting for the shared primitives and the historical scrollback view the player also needs. Reframed per user feedback "it also needs to be considered as to how they function with the turn update we have in the backlog," plus "there could also be a system log tab in the chat where a player could scroll back to see how things updated."_

- [ ] **Suggested actions as structured field (hybrid: prompt + schema + frontend).** The DM already writes these in prose at the end of every turn ("Do you strike with shadow magic, let Thalia's arrow find its mark, or use the key?") — they should be a structured array in the `<world_update>` block, not buried in narrative. Proposed schema addition: `suggestedActions: [{"label": "...", "tone": "aggressive|defensive|clever|..."}]`. Frontend renders as clickable pills under the command bar; clicking types the label into the input (does NOT auto-submit — player still reviews). Frontend supplements with rule-based "always-available" actions ("Look around", "Rest", "Wait"). Tiny schema addition + small bullet in `DM_SYSTEM_PROMPT` + small frontend component. No extra LLM call — the DM emits in its existing response. Graceful fallback when the DM forgets: show the rule-based standards only.
      _Discovered: 2026-04-14 | Context: the DM always ends turns with choice-prompts but they're buried in prose; surfacing them as UI commits the player to a cleaner interaction model_

- [ ] **Exits / navigation (schema addition + frontend).** Exits belong as a property of the Location entity, not as a top-level world field. Extend the location schema with `exits: [{"direction": "north", "destination": "Hollowed Temple"}]`. Frontend renders a compass / directions panel tied to the player's current location; clicking an exit types e.g. "I head north toward the Hollowed Temple" into the command bar. DM prompt bullet asks it to populate exits whenever introducing a new location. Additive schema change, no extra LLM call. Same DM-forgets fallback story as suggested actions. Lower urgency than #1 and #2 — only matters when movement is a gameplay axis, which it isn't yet.
      _Discovered: 2026-04-14 | Context: paired with suggested actions — together they give the player explicit verbs and explicit nouns to work with_

**Relation to the Entity Sweeper item in "Engine Package":** Items #2 and #3 here (suggested actions, exits) are things the DM mentions in prose but doesn't always emit as state — the same pattern as the cloak case that motivated the Entity Sweeper. The Sweeper's second-pass extraction model could generate these as a fallback when the DM forgets. Item #1 (turn-delta feedback) is orthogonal — pure frontend derivation, no extraction needed.

---

## Developer Experience

- [ ] Add unit and integration tests for `apps/sentinel-ui/` — Zustand stores, API client, and key components. See `docs/TESTING.md` "Near-term test work" item #1: vitest + @testing-library/react land alongside the Panel UX primitives (`EntityCard`, `DeltaMessage`, `TabbedChat`) from ROADMAP item #1. The fixture-based primitive tests are the smallest possible unlock for frontend CI coverage.
      _Discovered: 2026-03-26 | Updated: 2026-04-14 | Context: flagged in PR #5 review; no tests exist for any of the 8 frontend phases; scoped to land with the Panel UX rewrite rather than as a standalone effort_



- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
