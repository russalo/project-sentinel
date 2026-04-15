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

## Smoke-Test Findings — 2026-04-15 Baseline Run

Twelve distinct failure classes surfaced during the 2026-04-15 live
smoke test walkthrough ("Zombie + Western + Cowboy Bob, 6 turns").
The full transcript lives at
[`docs/smoke-tests/2026-04-15-baseline.md`](./smoke-tests/2026-04-15-baseline.md)
and is preserved verbatim as the "turn 0, no walls" reference run
for the **minimum-viable-structure research loop** (see
`docs/VISION.md` § "The minimum-viable-structure research loop").
Do not fix the bugs in the transcript — it is a data point. Fix them
in the code, the prompt, and the schema, and let the harness measure
the delta.

The items below are ordered by severity. Each one notes which
existing BACKLOG section it belongs under or supersedes, so this
section is a catalog, not a duplication.

### Critical

- [ ] **Session boundary is not a world boundary — new sessions inherit all prior state on disk.** The WorldCreation form creates a fresh session UUID but does not wipe `data/state/core/`, so entities/items/locations/factions authored in prior sessions remain on disk and in the DM's context on the next "new world." Confirmed by the 2026-04-15 post-test observation: referencing "AR15" mapped onto a `Ray Gun` tracked from an earlier session. Also explains several ghost NPCs in the transcript (Meral Hult, Kael, Kessra Velm) that appeared without being in the current WorldCreation intro. This is not a new finding — the existing "World Identity & Multi-Session" item already documents the design gap — but the urgency tier is wrong: today this is an active bug that blocks reliable testing, not a v2 design question. Promote the world-identity ADR from "unanswered design question" to **prerequisite for the research loop and for any deterministic smoke-test harness**. See also the `just reset-world` enabler below as the minimum-viable unblocker.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test; post-test AR15→Ray Gun reference bleed. Supersedes urgency tier on the existing "World Identity & Multi-Session" item._

- [ ] **Over-eager reference resolution — DM snaps generic mentions to nearest tracked entity.** Even in a clean single world, the DM resolves generic references ("AR15," "a sword," "the guard") to the nearest canonical entity in its context instead of treating them as generic instances. In a world with thousands of swords, "I draw my sword" should not mean "I draw Excalibur." The schema has no concept of **entity singularity** — every tracked thing is treated as unique, and every generic mention is treated as if it must resolve to a tracked thing. Affects every entity type (items, NPCs, locations, factions). The fix is primarily a DM system prompt rule: *"Entities in your known-entity list are specific, named, canonical things. Treat generic references as new generic instances unless the player explicitly names a tracked entity. The world contains thousands of unnamed swords, guards, and cultists; your tracked list is a handful of named exceptions."* Longer term the schema gains a `singularity` field (`unique_named` vs `class_instance`), but the prompt rule is the cheapest highest-leverage wall and belongs in the floor, not the loop. This is arguably the single most valuable entry on this list because (a) lift is near-zero, (b) it partially resolves the lazy-fabrication and player-authored-entity bugs downstream, and (c) it cleanly separates "the canonical world" from "the infinite generic substrate."
      _Discovered: 2026-04-15 | Context: 2026-04-15 post-test AR15 reference bleed. Complementary to the session-boundary fix above: cross-session bleed brings the entity into context, singularity governs how the DM treats it once it's there. Both need to land together._

- [ ] **Lazy fabrication on extraction — Fact-Extractor invents prior values to make deltas consistent.** Observed twice in the transcript: Kessra Velm turn 4 (`hp —→100`, `level —→4`, `role —→neutral`) and Sally Carn turn 6 (`hp 85→100`, where 85 was never a recorded prior value). The extractor is forging history to produce schema-valid upserts for entities that never had those fields set. This corrupts ADR 0001's core premise — **git-as-canonical-store requires the files to be truthful**, and `git log` will contain numbers that were never real. Root cause is almost certainly that the extractor prompt treats every entity it sees in context as something that must have a complete-ish record, so it materializes missing fields with plausible values instead of leaving them null. Fix: the extractor prompt should only emit deltas for fields that actually changed in the narrative, and should never fabricate prior values. Needs engine-side schema work too — the `update` operation should probably reject deltas whose prior value was never recorded (requires fs-manager to round-trip the prior state). Covers characters today; likely applies to items/locations/factions too.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 4 and 6. Belongs to the engine package; the Fact-Extractor already exists at `engine/agents/fact_extractor.py` — this is a prompt + validation fix, not a new agent._

- [ ] **Player character is stored in the same schema bucket as NPCs — no ownership distinction.** Russalo's first entity appearance in turn 4 revealed that the PC has no structural protection from DM-authored deltas. The DM leveled the player up (`level 1→2`) for casting a vanity illusion; later turns dropped HP based on prose. There is no `player_owned` flag on PC fields, no "DM cannot write to player sheet" rule in the schema or the extractor. In any TTRPG-shaped game, PC identity fields (class, level, HP, name) are owned by the player, not the narrator. Fix: (a) mark PC identity fields `x-sentinel-player-owned: true` in the schema analogous to `x-sentinel-protected: true`, (b) have fs-manager reject updates to player-owned fields unless the request carries an explicit `player_authored: true` flag, and (c) add a DM system prompt rule: *"Player character fields (class, level, HP, stats) are owned by the player. You may narrate consequences of actions but you may not rewrite PC identity fields via `<world_update>`."* Related to the authority gap but narrower and structurally addressable. This is the single most important wall the project needs for any TTRPG-shaped experience.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turn 4 (Russalo level 1→2 on a cosmetic spell); turn 6 (Russalo hp 100→75 from "rot seeped back"). Belongs in the schema layer and the DM prompt._

### High

- [ ] **Player-authored entity gate — players cannot mint mechanically-significant items, NPCs, or implied classes via prose.** The authority gap is wider than "no ray gun." Over the smoke test the player minted (a) a ray gun by typing "take out my ray gun," (b) an NPC record for "Cowboy Bob" by typing "confront Cowboy Bob," (c) an implied character class by casting a spell the current class could not cast. Fix lives in the DM system prompt with two tiers: **ambient/inferred objects** (desk, window, bottle on a bar) → player can interact freely, DM improvises, no schema entry required; **mechanically significant items / named NPCs / capability changes** → must be introduced by the DM or pre-existing. Draft prompt rule: *"Players cannot introduce items of mechanical significance, named characters, or capabilities they do not possess. If a player references such a thing and it does not exist in the current scene, narrate the absence. Generic interactions with ambient objects are freely improvised."* Longer term this becomes a `player_authority` section in genre or persona TOML files so horror can be stricter ("you have only what you brought") and sandbox fantasy can be looser. See also the entity-singularity rule above — these two rules work together.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 1, 3, and 4. Supersedes the "Player Actions & Game Mechanics" section's implicit assumption that action vocabulary alone is the unit of control — the vocabulary is only half; the other half is what entities and capabilities the player can reference into existence._

- [ ] **Schema enum fields accept free-text — `status` and `type` are chaos fields.** The transcript shows `status alive→unknown→alive` (for chickens), `type fortress→palace garden→castle` within three turns, and `role —→neutral` lazy-fabricated. The `type` field on locations in particular has no controlled vocabulary — any descriptive phrase the DM writes is accepted as a valid value. Same problem on `status` on characters (`alive`/`unknown` is lossy enough that "alive but transformed into a chicken" collapses to "unknown," then flips back to "alive" when the DM remembers they're still around). Fix: declare explicit enums in the JSON schemas for `status`, `type`, `role`, and friends; reject free-text; if the DM wants to represent a novel state, that's a separate `modifiers: []` field, not a type-name rewrite. This also clears the way for the "entity modifiers as a distinct field" item below.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 1–6. Schema work in `schemas/apply_world_update.schema.json` and the entity type schemas under `schemas/entities/` (if they exist as separate files) or the inlined entity schemas referenced by apply_world_update._

- [ ] **Ungrounded numeric stats — `tension`, `level`, `hp`, `danger` move on narrative vibes with no rules.** Observed 7+ times in the transcript. `tension` moved up for a naked laughing sprint and down for a seduction spell. `level` moved up on a vanity illusion and sideways on an NPC getting prettier. `hp` dropped because "rot seeped back" and went up on an NPC because she became human. `danger` dropped because the scene got prettier. None of these have rules explaining the delta; the DM is just making numbers fit the prose. This is the mechanical-resolution open question (see `docs/VISION.md`) showing its teeth in practice. The tightest fix is a DM system prompt rule: *"You may narrate freely, but you may not emit deltas to numeric stats (`hp`, `level`, `tension`, `danger`) unless the narration describes a concrete cause (combat, stress, explicit reward, explicit cost). If you cannot name the cause in the prose, do not move the number."* Longer term this gets replaced with a rule-based resolution layer per-genre. See also the entity-singularity and authority rules above — the pattern is the same: tight prompt walls first, schema enforcement next, rule-based systems last.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test, every turn. Related to the existing "Player Actions & Game Mechanics" section's "Resolution model" deferred decision, but narrower — this is about preventing phantom deltas, not about building a full dice system._

- [ ] **Narrator persona name collides with entity namespace.** Turn 3 revealed that when the player asked to confront "Cowboy Bob" (the name of the active DM persona), the Fact-Extractor materialized a `Cowboy Bob` character record as an `enemy` with a holstered six-shooter. The persona name is metadata about *who is telling the story*, not a thing that exists inside the story. The schema has no concept of "narrator" vs "character," so any capitalized name the DM writes is fair game for entity creation — including the DM's own persona. Fix: reserve persona names in the entity-authoring path. Either (a) tag the active persona name as a protected field the same way `unique_id` is, and have fs-manager reject creation of entities whose name matches the active persona; or (b) add a DM system prompt rule forbidding self-reference-as-character. Option (a) is structurally stronger.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turn 3. Structural bug in the schema + extractor boundary._

- [ ] **Location field carrying state via string concat — `"palace garden (collapsing)"`.** Turn 6 wrote the location value `"palace garden (collapsing)"` into Russalo's, Sally's, and Kessra's records. The parenthetical is a status modifier being smuggled into the name field. Once written, no future query against `location="palace garden"` will match these entities. Fix: locations need a separate `modifiers: []` or `status: str` field distinct from the canonical name. Same shape as the proposed `modifiers` resolution to the enum-field chaos item above — location is just another entity type with the same disease. Probably solved by a single schema pass that introduces modifier fields on every entity type that currently conflates name with state.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turn 6._

### Medium

- [ ] **Duplicate entity spawning on rename.** Turn 6 emitted both a location-move for existing entities *to* `"palace garden (collapsing)"` AND a `+ palace garden · location` create in the same update payload. The extractor double-booked the same conceptual place. Fix is probably a post-extraction dedupe pass (or a validation rule in fs-manager) that notices "this create and this move reference the same locale" and merges them. Depends on the entity-modifier work above to even be meaningful, because today "palace garden" and "palace garden (collapsing)" aren't considered the same entity.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turn 6._

- [ ] **Item capabilities are unbounded — the ray gun turned people into chickens, then reshaped reality, then summoned orgies.** No defined capability on tracked items; the item acts as whatever the current prose demands. Fix: item records should include a `capabilities: []` field constrained to the genre's action catalog. See the existing "Player Actions & Game Mechanics" section — this is the item-facing side of that work. Not a separate piece; note here to make sure the action catalog work remembers that items scope actions too.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 1, 3, 4, 5._

### Design / UX

- [ ] **Character class field has no compatibility validation.** The WorldCreation form's `CLASS` input is free text. During the smoke test the player typed `Zombie` into a Western campaign with no warning, compatibility check, or validation against genre. At minimum, character class should be either a selector populated from preset content (similar to persona/mood) or a free-text input that runs a compatibility pass against the selected genre and warns on mismatch. Longer term, character classes should become their own preset content (`data/lore/core/presets/classes/<class>.toml` with `compatible_genres` metadata) following the same pattern PR #39 shipped for genres/personas/moods/regions, so the framework generalizes one step further. See also the existing "DM Personas & Content Framework" item's "generalize the pattern to the rest of the framework" tail — classes, action catalogs, and mechanical resolution presets all slot into the same extension path.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test — "Zombie" class typed into a Western, Cowboy Bob persona session with zero pushback from the form._

- [ ] **Tone and Mood selectors have overlapping value lists — "Humorous" appears in both.** The WorldCreation form currently exposes Tone (Layer 1 free-form label) and Mood (Layer 2 preset content bundle) as separate selectors, with overlapping options ("Humorous" is selectable in both). The underlying distinction is real — Tone is a one-line label pushed into the CREATION CONTEXT block, Mood is a full preset TOML fragment injected into WORLD FOUNDATIONS — but the UX makes them look redundant or contradictory. Three possible fixes: (a) disambiguate the value lists so no option appears in both, (b) consolidate into a single dimension (mood absorbs tone or vice versa), (c) make the relationship hierarchical (mood options are filtered by selected tone). Decision deferred; file for a future WorldCreation UX pass.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test — user observed the overlap while configuring the Cowboy Bob run._

- [ ] **AppShell welcome message is hardcoded to author "Oracle" regardless of persona.** In `apps/sentinel-ui/src/components/shell/AppShell.jsx`, the welcome message seeded on mount uses `author: 'Oracle'` even when the player has selected The Chronicler or Cowboy Bob. Should read from `personaStore.personaName` (or be suppressed entirely when a session is already in progress). Cosmetic but confusing during smoke tests where the persona display in TopBar correctly shows the selected persona while the welcome line contradicts it.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test, observed on hard reload mid-session._

- [ ] **React Strict Mode produces two welcome messages on hard reload.** The welcome-message `useEffect` in `AppShell` checks `messages.length === 0` but Strict Mode fires the effect twice in development and the state update between the two firings isn't synchronous, so both invocations see an empty list and both call `addMessage`. Not reproducible in production builds but confusing during development. Fix: gate with a `useRef` flag rather than the messages-length check, or move welcome-seeding out of an effect into session initialization entirely (where it probably belongs anyway once the session lifecycle is sorted).
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test, observed on hard reload._

### Enablers (prerequisites for the research loop)

- [ ] **`just reset-world` recipe — minimum-viable world reset for isolated smoke-test runs.** Today there is no way to start a fresh world without manually `rm -rf`ing `data/state/core/` — and doing that naively breaks the git-backed invariant because the tree is version-controlled. A `just reset-world` recipe should (a) stage a clean `data/state/core/` to a known empty-but-valid state (probably a committed baseline), (b) create a reset commit via git-sync so the history is intact, and (c) optionally take a snapshot name so prior runs can be stashed for comparison. This unblocks the session-isolation problem without requiring the full world-identity ADR to land first, and it is the single cheapest thing that makes deterministic smoke testing possible. Explicitly *not* a replacement for the world-identity ADR — that ADR still needs to happen and should supersede this recipe when it lands.
      _Discovered: 2026-04-15 | Context: derived from the cross-session state bleed finding above — the research loop needs clean runs, and clean runs need a reset path that exists today._

- [ ] **Repeatable smoke test harness — scripted player inputs, deterministic seed, captured transcripts.** Today's walkthrough was manual. The minimum-viable-structure research loop (see `docs/VISION.md`) depends on being able to replay the same scenario across progressively stricter walls and diff the resulting transcripts. The harness needs: (a) a way to script player inputs as an ordered list, (b) a way to pin the LLM to a deterministic seed (temperature 0, fixed sampler config, and ideally a cached-response layer for regression testing even when the model is nondeterministic), (c) a capture format that records the full turn including narrative, world_update payloads, and schema validation errors, and (d) a diff tool that compares runs and highlights the deltas. Scope is non-trivial — probably lives in a new `tests/smoke/` tree that runs against a real backend with fixtures — and should be gated on (a) world reset working, (b) a "headless session" backend mode that doesn't need a browser. See also the existing deferred Playwright backlog item; this is the backend-shaped complement to that.
      _Discovered: 2026-04-15 | Context: derived from the 2026-04-15 baseline run. This harness is a prerequisite for the research loop; without it, every wall-addition PR is a single-point anecdote._

- [ ] **Vite 8 oxc replaces esbuild — `esbuild.jsx: 'automatic'` in `vite.config.js` is dead config.** PR #37 added an explicit `esbuild.jsx: 'automatic'` to make vitest's JSX transform work. Vite 8 has since moved to oxc as its primary transformer and the esbuild config is now a no-op (observed as a Vite startup log during 2026-04-15 smoke test setup). The vitest JSX transform is still working (tests pass), so nothing is broken; but the config should either be removed or migrated to whatever oxc equivalent Vite 8 exposes. Low priority but worth cleaning up before someone wastes an hour chasing it.
      _Discovered: 2026-04-15 | Context: noticed during PR #40 docs cleanup when the 2026-04-15 smoke test stack was brought up._

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

      _Updated 2026-04-15: The 2026-04-15 smoke test confirmed this isn't just an unanswered design question — it's an active bug. See the "Session boundary is not a world boundary" critical item in the Smoke-Test Findings section: starting a "new world" in the UI does not wipe `data/state/core/`, and entities (including a `Ray Gun` the player referenced via "AR15") bled across sessions. The urgency tier is now "prerequisite for the research loop and for any deterministic smoke-test harness," not v2 design. The `just reset-world` enabler in the same section is the minimum-viable unblocker while this ADR is drafted._

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
  2. ✅ Preset file layout defined and authored — `data/lore/core/presets/{genres,personas,moods,regions}/` under TOML. Regions are genre-scoped (`regions/<genre>/<slug>.toml`). Schema is minimal (`name`, `slug`, optional `compatible_*`, required `prompt_fragment`). No ADR written — layout is small enough to self-document via the shipped files and `backend/presets.py` docstring. Community pack composition is deferred to the DM Personas & Content Framework item.
  3. ✅ Minimum viable preset content authored for every current WorldCreation selector: 5 genres, 3 personas, 6 moods, 20 regions (4 per genre).
  4. ✅ Generation pipeline built — `backend/presets.py` loads presets, `backend/routes/session.py` resolves genre/persona/mood/region fragments on `POST /api/session/new` and threads them to `engine.IntroInput.{genre,persona,mood,region}_prompt`. Engine's `_build_intro_messages` injects them as a "WORLD FOUNDATIONS" paragraph block; `_creation_context_lines` suppresses the redundant bare label lines when a matching `*_prompt` is set.
  5. Next: **programmatic seed-entity population.** Region preset files currently describe their canonical NPCs, locations, and opening situations in prose inside `prompt_fragment`, which the LLM reads and typically honors — but there is no structured guarantee. Add an optional `seed_entities` TOML block to region files (characters, locations, factions, items with schema-valid fields), have the backend merge them into the initial `apply_world_update` payload *before* dispatching to fs-manager, so the canonical region fixtures land regardless of whether the DM mentions them. Depends on the "World identity, world_seed persistence, and multi-session semantics" ADR to settle whether regions are keyed per world or globally shared.
  6. Then expand preset coverage as the form grows — new tones, new personas beyond the three shipped, new genres (cosmic horror, post-apocalyptic, historical fiction), additional regions per genre.
      _Discovered: 2026-04-14 | Updated: 2026-04-15 | Context: Layer 2 steps 2–4 landed in the WorldCreation Layer 2 PR. The remaining seed-entity step is a structured-content step gated on the world identity ADR; preset coverage expansion is an ongoing worldbuilding task_

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

- [ ] **DM personas as framework content, not hardcoded behavior.** **Partially shipped in PR #39 (WC Layer 2).** The first half of this item — authored persona content + a backend loader + composition into the DM intro prompt — landed: 3 personas live as TOML files under `data/lore/core/presets/personas/`, `backend/presets.py` resolves them at session-create time, and `engine/agents/dm.py::_build_intro_messages` injects the resolved fragment as part of the "WORLD FOUNDATIONS" block above the existing "CREATION CONTEXT" block. PR #39 took a simpler one-TOML-file-per-preset layout instead of the per-persona-directory layout the original entry below envisioned (`persona.md` + `persona.json` + `system_prompt.md` + `voice_rules.md`); the simpler shape works for the current three personas and can be extended if a future persona needs richer composition. The original framework vision is below for reference; what's still aspirational is summarized at the bottom.

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
  1. ⏭️ Write an ADR capturing the persona (and general preset) framework: file layout, composition model, what's core-protected vs overridable, how `community.json` extends, how the engine loads and validates presets — **deliberately skipped in PR #39.** The author judged the file layout small enough to self-document via the shipped TOML files and the `backend/presets.py` docstring. If a future change needs the framework formalized (e.g., when community packs become real), write the ADR retrospectively.
  2. ✅ Migrate the existing `DM_SYSTEM_PROMPT` into the framework — **partial.** PR #39 ships three personas as `data/lore/core/presets/personas/<slug>.toml` files alongside the existing `engine/prompts/dm.py` `DM_SYSTEM_PROMPT`. The base contract was NOT extracted into a separate file; the `DM_SYSTEM_PROMPT` constant still lives in code as the base, and the persona TOMLs contribute the per-persona `prompt_fragment` that gets composed in via the WORLD FOUNDATIONS block. If/when a community persona needs to override the base contract, that extraction becomes necessary; until then the simpler shape is fine.
  3. ✅ Backend preset loading — **shipped.** `backend/presets.py` exposes `load_preset(preset_root, type, id, *, genre=None)` and `get_prompt_fragment(...)`. Called from `backend/routes/session.py::new_session` for each of `genres`, `personas`, `moods`, `regions`. Lenient (missing files return `None`, falls through to Layer 1 free-form labels).
  4. ⏳ Extend `schemas/community_manifest.schema.json` to declare `personas`, `action_sets`, `genres`, `regions` as declarable pack content types — **still pending.** The community pack composition pathway doesn't exist yet; PR #39 only ships the core layer.
  5. ✅ Wire the WorldCreation form to actually use the selected persona — **shipped via Layer 1 (PR #20) + Layer 1.5 (PR #33) + Layer 2 (PR #39).** The frontend sends `personaId` (and `personaName`/`personaDescription` as fallback metadata); the backend resolves the id to a preset fragment first, falls back to the descriptive fields if no preset matches, falls back to the bare id if even those are missing.
  6. ✅ Author a second persona to validate the composition pipeline — **three personas shipped:** Oracle, The Chronicler, Cowboy Bob. Each has a distinct `prompt_fragment` and the WORLD FOUNDATIONS block carries them through into the DM intro prompt, so picking different personas now produces meaningfully different opening narratives.
  7. ⏳ Document the contributor pathway in `CONTRIBUTING.md` — **still pending.** No "how to author a new DM persona" guide yet.

  **Status summary (as of 2026-04-15, post-PR #39):** Core persona content + loader + composition pipeline are live. Community pack pathway, contributor docs, the per-persona-directory layout (vs. one-TOML-per-preset), and generalization to action catalogs / dice systems / etc. are still future work. This entry stays open to track the remaining pieces.

      _Discovered: 2026-04-14 | Updated: 2026-04-15 | Context: user said "And DMs too. We want the world to grow, but based on existing frameworks." — reaffirming that the DM persona system should plug into the Core/Community framework documented in ARCHITECTURE.md §§1–3, not be hardcoded as it currently is. Step 2/3/5/6 of the order-of-operations checklist landed in PR #39; steps 1/4/7 are still pending_

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

- [ ] **Expand `apps/sentinel-ui/` test coverage to stores and hooks.** vitest + @testing-library/react infrastructure landed with the first 34 tests covering `utils/delta.js` and the `EntityCard` + `DeltaMessage` primitives. The next slice is the Zustand stores (`chatStore`, `worldStore`, `uiStore`, `personaStore`) and the `useDMStream` hook — the latter is the trickiest because it touches `fetch` and the SSE event parser, but it's also the highest value for catching turn-loop regressions. Tests should mock `fetch` with a small SSE-event-emitting fake. Defer until either a regression makes one of these load-bearing or someone wants to spend a focused session expanding coverage. See `docs/TESTING.md` "Near-term test work" for the full framing.
      _Discovered: 2026-03-26 | Updated: 2026-04-15 | Context: original "no frontend tests" gap closed by the vitest infrastructure PR; this is the followup item for the rest of the surface_



- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
