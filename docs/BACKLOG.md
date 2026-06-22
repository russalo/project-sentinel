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

- [ ] **Auth strategy — implement ADR 0003 (closed beta).** The *decision* is made: two paths were on the table — (1) simple shared-secret/API-key gate for a public deployment, (2) outsourced JWT (Auth0/Clerk/Supabase) — and **[ADR 0003](adr/0003-access-gating-and-public-exposure.md) (Accepted, 2026-06-03)** chose path (1) for the closed-beta phase: a single shared invite gate at the Caddy edge (no accounts), per-world capability tokens, and lenient rate-limiting. Path (2) (per-user accounts) is explicitly deferred to a future open-signup phase (ADR 0003 § "Out of scope — vision"). (The Django User model path is off the table now that Django has retired; the SSE stream conflicts with neither — auth runs before the stream opens.) Implementation is sliced A+B (backend access layer) then C (edge/ops). **Slices A+B landed 2026-06-03** (`feat/adr-0003-access-layer`): per-world stateless HMAC session tokens (`backend/auth/`), enforced on `/stream` + `/world` GET/DELETE via the `X-Sentinel-World-Token` header (`backend/auth/access.py`); per-IP world-creation + per-world turn rate limits + a global daily LLM-call ceiling (`backend/ratelimit.py`); a SPA per-world token store (`apps/sentinel-ui/src/api/worldToken.js`). **All opt-in — dormant unless `SENTINEL_SESSION_TOKEN_SECRET` / `SENTINEL_RL_*` / `SENTINEL_LLM_DAILY_CEILING` are set** — so local & tailnet play stays anonymous/unthrottled; a startup log line states the posture (enforce-only-when-configured, ratified 2026-06-03). **Slice C (edge/ops) landed 2026-06-04** (`feat/adr-0003-edge-gate-systemd`): the MCP network-isolation invariant (A2 — servers refuse all-interfaces binds; backend config-agreement check; see the separate item below), a committed Caddy `basic_auth` invite-gate template (`infrastructure/caddy/Caddyfile.example`, guarded by `tests/test_caddy_invariant.py` so it never proxies `:8010`/`:8012` and keeps `/healthz` un-gated), and systemd unit templates for the backend + both MCP servers (`infrastructure/systemd/`; Caddy documented as system-managed). Deploy runbook in `docs/WORKSPACE.md` § "Production deployment". **What remains is the A4 operational cutover** (a runbook step, not code): on origin-core set `SENTINEL_WORLDS_ROOT` + `SENTINEL_SESSION_TOKEN_SECRET` + the `SENTINEL_RL_*`/`SENTINEL_LLM_DAILY_CEILING` knobs across all three services, supply the Caddy invite hash, and flip the gate live — behind the tracer-soak gate. Then path (2) (accounts) when open signup is on the table.
      _Discovered: 2026-03-27 | Updated: 2026-06-03 | Context: originally Django-era planning; trimmed to viable FastAPI-era options only; Slices A+B (token + rate-limit) implemented 2026-06-03_

- [ ] **Stale `POSTGRES_*` vars in the live `infrastructure/.env` (NOT the template).** **Correction (2026-06-04, verified against disk):** the chezmoi template `.chezmoi/dot_infrastructure/dot_env.tmpl` is **already Postgres-free** — it does not emit `POSTGRES_USER/PASSWORD/DB`. The stale vars (and a real-looking password) live only in the *generated* `infrastructure/.env` on origin-core, left over from an older template version that was never regenerated. So there's **nothing to prune in the template**; the fix is operational: **re-run `just env` on origin-core** to regenerate `.env` from the current template (which drops the stale `POSTGRES_*` and now also adds the `SENTINEL_*` cutover knobs — A4-prep). No code (`backend/`, `engine/`, `mcp-servers/`) references any `POSTGRES_*`. Related note: `CHROMA_AUTH_PROVIDER`/`CHROMA_AUTH_CREDENTIALS_FILE` are emitted empty → ChromaDB runs unauthenticated (a security note for public-exposure work, not a rotation secret).
      _Discovered: 2026-06-03 | Corrected: 2026-06-04 | Context: surfaced during a tailnet credential inventory. The original claim ("emitted by the template on every just env") was wrong — I checked the live `.env` but not the template (verify-against-disk miss). The template is clean; the live `.env` is just stale. The only live external credential is `OPENAI_API_KEY`, a LiteLLM-proxy virtual key (→ tailnet gateway `100.119.83.49:4000`, model qwen3-32b), not a real OpenAI key._

---

## Documentation Drift

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

- [x] **Session boundary is not a world boundary — new sessions inherit all prior state on disk.** ✅ **RESOLVED by ADR 0002 per-world isolation.** `backend/routes/session.py::new_session` mints `world_id = uuid.uuid4()` at every session-create and provisions a fresh per-world repo via `engine.init_world(config, world_id=...)`; with `SENTINEL_WORLDS_ROOT` armed in production each world's data lives at `<WORLDS_ROOT>/<world_id>/data/` with no shared tree to bleed from. Verified 2026-06-22 against the running backend on origin-core.
      _Discovered: 2026-04-15 | Closed: 2026-06-22_

- [ ] **Over-eager reference resolution — DM snaps generic mentions to nearest tracked entity.** Even in a clean single world, the DM resolves generic references ("AR15," "a sword," "the guard") to the nearest canonical entity in its context instead of treating them as generic instances. In a world with thousands of swords, "I draw my sword" should not mean "I draw Excalibur." The schema has no concept of **entity singularity** — every tracked thing is treated as unique, and every generic mention is treated as if it must resolve to a tracked thing. Affects every entity type (items, NPCs, locations, factions). The fix is primarily a DM system prompt rule: *"Entities in your known-entity list are specific, named, canonical things. Treat generic references as new generic instances unless the player explicitly names a tracked entity. The world contains thousands of unnamed swords, guards, and cultists; your tracked list is a handful of named exceptions."* Longer term the schema gains a `singularity` field (`unique_named` vs `class_instance`), but the prompt rule is the cheapest highest-leverage wall and belongs in the floor, not the loop. This is arguably the single most valuable entry on this list because (a) lift is near-zero, (b) it partially resolves the lazy-fabrication and player-authored-entity bugs downstream, and (c) it cleanly separates "the canonical world" from "the infinite generic substrate."
      _Discovered: 2026-04-15 | Context: 2026-04-15 post-test AR15 reference bleed. Complementary to the session-boundary fix above: cross-session bleed brings the entity into context, singularity governs how the DM treats it once it's there. Both need to land together._
      _Updated: 2026-06-02: Prompt-wall half shipped — the "Entity singularity" rule under STATE DISCIPLINE in `engine/prompts/dm.py`. Stays open for the structural remainder: the `singularity` schema field (`unique_named` vs `class_instance`), and pairing with the session-boundary/world-isolation fix — the prompt rule curbs in-session over-resolution, but cross-session bleed still feeds foreign entities into the DM's context._

- [ ] **Lazy fabrication on extraction — Fact-Extractor invents prior values to make deltas consistent.** Observed twice in the transcript: Kessra Velm turn 4 (`hp —→100`, `level —→4`, `role —→neutral`) and Sally Carn turn 6 (`hp 85→100`, where 85 was never a recorded prior value). The extractor is forging history to produce schema-valid upserts for entities that never had those fields set. This corrupts ADR 0001's core premise — **git-as-canonical-store requires the files to be truthful**, and `git log` will contain numbers that were never real. Root cause is almost certainly that the extractor prompt treats every entity it sees in context as something that must have a complete-ish record, so it materializes missing fields with plausible values instead of leaving them null. Fix: the extractor prompt should only emit deltas for fields that actually changed in the narrative, and should never fabricate prior values. Needs engine-side schema work too — the `update` operation should probably reject deltas whose prior value was never recorded (requires fs-manager to round-trip the prior state). Covers characters today; likely applies to items/locations/factions too.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 4 and 6. Belongs to the engine package; the Fact-Extractor already exists at `engine/agents/fact_extractor.py` — this is a prompt + validation fix, not a new agent._
      _Updated: 2026-06-02: Prompt-wall half shipped — the "No invented history" rule under STATE DISCIPLINE in `engine/prompts/dm.py` (note: the Fact-Extractor is a pure parser, so the fabrication originates in the DM's emitted block, not the extractor). Stays open for the structural half: engine/fs-manager-side validation that rejects deltas whose prior value was never recorded (requires round-tripping prior state)._

- [ ] **Player character is stored in the same schema bucket as NPCs — no ownership distinction.** Russalo's first entity appearance in turn 4 revealed that the PC has no structural protection from DM-authored deltas. The DM leveled the player up (`level 1→2`) for casting a vanity illusion; later turns dropped HP based on prose. There is no `player_owned` flag on PC fields, no "DM cannot write to player sheet" rule in the schema or the extractor. In any TTRPG-shaped game, PC identity fields (class, level, HP, name) are owned by the player, not the narrator. Fix: (a) mark PC identity fields `x-sentinel-player-owned: true` in the schema analogous to `x-sentinel-protected: true`, (b) have fs-manager reject updates to player-owned fields unless the request carries an explicit `player_authored: true` flag, and (c) add a DM system prompt rule: *"Player character fields (class, level, HP, stats) are owned by the player. You may narrate consequences of actions but you may not rewrite PC identity fields via `<world_update>`."* Related to the authority gap but narrower and structurally addressable. This is the single most important wall the project needs for any TTRPG-shaped experience.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turn 4 (Russalo level 1→2 on a cosmetic spell); turn 6 (Russalo hp 100→75 from "rot seeped back"). Belongs in the schema layer and the DM prompt._

### High

- [ ] **Player-authored entity gate — players cannot mint mechanically-significant items, NPCs, or implied classes via prose.** The authority gap is wider than "no ray gun." Over the smoke test the player minted (a) a ray gun by typing "take out my ray gun," (b) an NPC record for "Cowboy Bob" by typing "confront Cowboy Bob," (c) an implied character class by casting a spell the current class could not cast. Fix lives in the DM system prompt with two tiers: **ambient/inferred objects** (desk, window, bottle on a bar) → player can interact freely, DM improvises, no schema entry required; **mechanically significant items / named NPCs / capability changes** → must be introduced by the DM or pre-existing. Draft prompt rule: *"Players cannot introduce items of mechanical significance, named characters, or capabilities they do not possess. If a player references such a thing and it does not exist in the current scene, narrate the absence. Generic interactions with ambient objects are freely improvised."* Longer term this becomes a `player_authority` section in genre or persona TOML files so horror can be stricter ("you have only what you brought") and sandbox fantasy can be looser. See also the entity-singularity rule above — these two rules work together.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 1, 3, and 4. Supersedes the "Player Actions & Game Mechanics" section's implicit assumption that action vocabulary alone is the unit of control — the vocabulary is only half; the other half is what entities and capabilities the player can reference into existence._

- [ ] **Schema enum fields accept free-text — `status` and `type` are chaos fields.** The transcript shows `status alive→unknown→alive` (for chickens), `type fortress→palace garden→castle` within three turns, and `role —→neutral` lazy-fabricated. The `type` field on locations in particular has no controlled vocabulary — any descriptive phrase the DM writes is accepted as a valid value. Same problem on `status` on characters (`alive`/`unknown` is lossy enough that "alive but transformed into a chicken" collapses to "unknown," then flips back to "alive" when the DM remembers they're still around). Fix: declare explicit enums in the JSON schemas for `status`, `type`, `role`, and friends; reject free-text; if the DM wants to represent a novel state, that's a separate `modifiers: []` field, not a type-name rewrite. This also clears the way for the "entity modifiers as a distinct field" item below.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test turns 1–6. Schema work in `schemas/apply_world_update.schema.json` and the entity type schemas under `schemas/entities/` (if they exist as separate files) or the inlined entity schemas referenced by apply_world_update._

- [ ] **Ungrounded numeric stats — `tension`, `level`, `hp`, `danger` move on narrative vibes with no rules.** Observed 7+ times in the transcript. `tension` moved up for a naked laughing sprint and down for a seduction spell. `level` moved up on a vanity illusion and sideways on an NPC getting prettier. `hp` dropped because "rot seeped back" and went up on an NPC because she became human. `danger` dropped because the scene got prettier. None of these have rules explaining the delta; the DM is just making numbers fit the prose. This is the mechanical-resolution open question (see `docs/VISION.md`) showing its teeth in practice. The tightest fix is a DM system prompt rule: *"You may narrate freely, but you may not emit deltas to numeric stats (`hp`, `level`, `tension`, `danger`) unless the narration describes a concrete cause (combat, stress, explicit reward, explicit cost). If you cannot name the cause in the prose, do not move the number."* Longer term this gets replaced with a rule-based resolution layer per-genre. See also the entity-singularity and authority rules above — the pattern is the same: tight prompt walls first, schema enforcement next, rule-based systems last.
      _Discovered: 2026-04-15 | Context: 2026-04-15 smoke test, every turn. Related to the existing "Player Actions & Game Mechanics" section's "Resolution model" deferred decision, but narrower — this is about preventing phantom deltas, not about building a full dice system._
      _Updated: 2026-06-02: Prompt-wall half shipped — the "Grounded numbers" rule under STATE DISCIPLINE in `engine/prompts/dm.py` forbids moving health/level/tension/danger/power without a narrated cause (field names corrected to match the schema — `health`, not `hp`). Stays open for the longer-term per-genre rule-based resolution layer._

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

### Enablers (prerequisites for the research loop)

- [ ] **Repeatable smoke test harness — scripted player inputs, deterministic seed, captured transcripts.** Today's walkthrough was manual. The minimum-viable-structure research loop (see `docs/VISION.md`) depends on being able to replay the same scenario across progressively stricter walls and diff the resulting transcripts. The harness needs: (a) a way to script player inputs as an ordered list, (b) a way to pin the LLM to a deterministic seed (temperature 0, fixed sampler config, and ideally a cached-response layer for regression testing even when the model is nondeterministic), (c) a capture format that records the full turn including narrative, world_update payloads, and schema validation errors, and (d) a diff tool that compares runs and highlights the deltas. Scope is non-trivial — probably lives in a new `tests/smoke/` tree that runs against a real backend with fixtures — and should be gated on (a) world reset working, (b) a "headless session" backend mode that doesn't need a browser. See also the existing deferred Playwright backlog item; this is the backend-shaped complement to that.
      _Discovered: 2026-04-15 | Context: derived from the 2026-04-15 baseline run. This harness is a prerequisite for the research loop; without it, every wall-addition PR is a single-point anecdote._
      _Updated: 2026-06-02: Prerequisite (a) "world reset working" is now satisfied — `just reset-world` shipped (`scripts/reset-world.py`). Remaining gates: (b) a headless turn-runner (no browser), plus the harness proper (scripted-input fixtures, cached-response determinism via the engine's `client=` injection, capture format, diff tool)._

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

  **Before implementation, write an ADR.** It should cover: the one-world-per-clone decision (or a decision to support multiplexing), the `genesis` block schema, the commit message format change, and the frontend UX for resume/new-session-in-world. Probably 200–400 lines, roughly half the length of ADR 0001. **→ Drafted as [ADR 0002](adr/0002-world-identity-and-isolation.md) (Proposed, 2026-06-02)** — recommends repo-per-world isolation, `world_id`/genesis, per-world write locking, and `/w/<world_id>` routing, to reach concurrent isolated worlds for public test users. Auth/public-exposure deferred to a follow-on ADR (0003).
      _Discovered: 2026-04-14 | Context: user asked "the git-sync is per world seed & session? How do we track?" during the engine → git-sync wiring PR, when they saw commits tagged with session_id in the git log. The honest answer is: per-session only, world_seed isn't persisted anywhere, and multi-session-same-world vs multi-world-per-instance isn't decided — it's all implicit today. This item captures the design gap before any of the World Generation / Player Actions / DM Personas Framework items try to build on top of "what does a world mean."_

      _Updated 2026-04-15: The 2026-04-15 smoke test confirmed this isn't just an unanswered design question — it's an active bug. See the "Session boundary is not a world boundary" critical item in the Smoke-Test Findings section: starting a "new world" in the UI does not wipe `data/state/core/`, and entities (including a `Ray Gun` the player referenced via "AR15") bled across sessions. The urgency tier is now "prerequisite for the research loop and for any deterministic smoke-test harness," not v2 design. The `just reset-world` enabler in the same section is the minimum-viable unblocker while this ADR is drafted._
      _Closed 2026-06-22: The session-boundary bug is now resolved end-to-end. ADR 0002 Slices 1–5 have shipped, the operational cutover (Slice 6 / Path A / A4) is armed on origin-core (`SENTINEL_WORLDS_ROOT=/home/russellp/sentinel-worlds`), and `backend/routes/session.py::new_session` mints a fresh `world_id` + provisions a clean per-world repo via `engine.init_world` on every create. No cross-world state can bleed because each world's `data/` tree lives in its own directory + git repo. The smoke-test Critical item is closed; the ADR 0002 implementation item below stays open for its residual Slice 5 resume-fidelity follow-ups._

- [ ] **ADR 0002 implementation — remaining slices.** Slices 1–4 plus the bulk of Slice 5 (resume completeness, the "my worlds" picker, hard-delete teardown) have landed. Slice 1 (world_id threaded through backend + git-sync commit messages); Slice 2 (MCP servers resolve a per-world tree under `SENTINEL_WORLDS_ROOT`, UUID-validated + traversal-guarded; engine dispatch + backend threading); Slice 3 (provisioning + world-aware reads + tracer-soak gate); Slice 4 (resume hydration + `/w/<world_id>` URLs); Slice 5 (teardown + "my worlds" picker + resume completeness — see "remaining" below). Cross-process locking landed (Path A / A1, 2026-06-03 — see sub-item). The MCP network-isolation invariant + cutover config-agreement check landed (Path A / A2, 2026-06-04). ADR 0003 Slice C landed (Path A / A3, 2026-06-04 — Caddy invite-gate template + systemd unit templates). **Remaining:** residual Slice 5 resume-fidelity follow-ups (see the Slice 5 sub-item below) and the **operational cutover** itself (Path A / A4 — an env flip + edge deploy, not code; see `docs/WORKSPACE.md` § "Per-world isolation cutover" / "Production deployment"). Backend world provisioning at session-create (`engine.init_world`) is wired — it lands as Slice 3 behavior (`backend/routes/session.py`).
    - ✅ **Slice 3 — provisioning + world-aware reads + tracer-soak gate (landed 2026-06-03).** The backend routes reads per-world: `/api/stream` locates a turn's world from its `session_id` (`find_session_data_dir`) — the session is the authoritative routing key, so no client-supplied `world_id` is trusted and the cutover needs no frontend change; `training.py` + the export script scan per-world. Worlds are **provisioned** at creation via git-sync `init_world` (`git init` + baseline + initial commit; idempotent on a valid HEAD; completes a half-provisioned repo; no-op pre-cutover). The **tracer-soak gate** (`tests/test_world_isolation_tracer_soak.py`) proves zero cross-world leak under concurrency — it caught and drove the fix for a real git-sync cwd race (`repo.index.add` → subprocess `repo.git.add`). Static-shared assets (`schemas/`, presets, core-lore codex) are NOT relocated. **The cutover is an operational env flip, not code** (`docs/WORKSPACE.md` § "Per-world isolation cutover"); leaving `SENTINEL_WORLDS_ROOT` unset keeps the shared-tree default. Resolves the Codex "session reads" and gemini "static/mutable split" findings from the Slice 2 review.
      _Known perf note: `find_session_data_dir` scans every world dir to locate a session on each `/api/stream` turn — O(worlds), fine at test scale. If world count grows, add a `session_id → world_id` index (or carry an authenticated world_id once ADR 0003 auth lands) instead of scanning._
    - **Cutover config-agreement hard check (fs-manager).** The Slice 3 cutover requires backend + fs-manager + git-sync to all have `SENTINEL_WORLDS_ROOT` set. Today: git-sync disagreement is hard-caught (session-create 502s on `init_world` → `skipped`), and both MCP servers now expose `worlds_root` in `/health` for manual/`just health` verification — but **fs-manager** disagreement (backend+git-sync per-world, fs-manager still shared) is *not* auto-detected: `init_world` succeeds, fs-manager writes ignore `world_id` → land in the shared tree, and the backend then reads the empty per-world tree → the new session 400s on its next turn. Fix: a backend startup (or first-session) assertion that pings both servers' `/health` and refuses per-world mode unless both report `worlds_root: true` (symmetric with the git-sync check). _(Codex P1 on the Slice 3 PR; deferred as ops hardening — the var is default-off and operator-flipped behind a runbook.)_
    - ✅ **Slice 4 — frontend `/w/<world_id>` routing + resume (landed 2026-06-03).** The game plays at a world's own URL (shareable + refresh-surviving); `GET /api/world/<world_id>` rebuilds the scroll from the turn log on a fresh load (session is the routing key — no client-trusted world_id); `/` redirects to `/create`; the session record now persists `player_character_class`. The review swarm caught + drove fixes for real cross-world bleeds (a failed load left the prior world's chat; a world-switch left the prior world's panel entities → added `worldStore.reset()`) and resume-fidelity gaps (persona name + character class). Resume follow-ups (deferred, test-scale-acceptable): (a) the session record persists the persona *display name* but not `persona_id`/mood list, so resume restores the persona name (TopBar/author) but not the mood dropdown — persist persona_id+mood on the session (pairs with the genesis/`world_seed` persistence item) to fully restore; (b) `find_world_session` picks the most-recent session by mtime, ignoring `active` — fine at 1-session-per-world, but prefer `active` (and a logical ordering, not mtime) once worlds have multiple sessions; (c) legacy/shared mode reads+parses every session file to filter by `world_id` (O(all sessions)) — add a `session_id→world_id` index if the shared tree grows. _(All raised by the Slice 4 review swarm.)_
    - ◑ **Slice 5 — world lifecycle.** Landed 2026-06-03: (1) *resume completeness* — the session persists `persona_id`+`mood`, `GET /api/world/<id>` returns them + a `worldState` block, and `/w/<id>` resume restores the persona and rehydrates the world-state panels (not just the narrative); (2) *"my worlds" picker* — `GET /api/worlds` (`iter_worlds`, validated/canonical world_ids, most-recent first) + the `/` route is now a `WorldList` picker (resume → `/w/<id>`, or new). _Perf note: `/api/worlds` is O(worlds) — stats each world's latest session + re-reads it per world; fine at test scale, add a lightweight index if world count grows._ (3) *world teardown (hard delete)* — git-sync `teardown_world` (per-world: `rmtree` the repo, UUID/traversal-guarded before any removal; legacy: `git rm` the world's session file — shared `state/core` entities aren't world-scoped so they're left, which is the pre-cutover limitation); `DELETE /api/world/<id>` (resolves the session, routes through git-sync — backend never deletes files directly); a confirm-gated delete button per `WorldList` card; `reset-world --teardown`. Provisioning entry point is wired at session-create (`backend/routes/session.py` calls `engine.init_world` when `SENTINEL_WORLDS_ROOT` is set; lands as Slice 3 behavior). Slice-5-resume follow-ups (deferred): (a) **persona available-mood list** isn't persisted (preset metadata), so resume restores the selected mood + id/name but the mood dropdown shows the store-default options — persist/resolve the persona's moods to fully restore; (b) **`day` is never persisted** (no day field on disk), so a resumed world always shows "Day 1" — pre-existing gap, fix with the genesis/`world_seed` persistence item; (c) ✅ **`WorldMetrics` numeric-tension display** — resolved: `tensionLabel()` normalizes numeric tension → label band in *both* `hydrate` (resume) and `applyUpdate` (live SSE), so `worldStore.tension` is consistently a string label and WorldMetrics renders a styled severity in both paths. (d) **Legacy-mode `worldState` isn't world-scoped:** `GET /api/world/<id>` reads `load_world_context` on the resolved data dir; in per-world mode that's the world's own tree (isolated), but in legacy/shared mode it's the global shared tree, so resuming one world shows the shared panel state. This matches the legacy live path (`stream.py` reads the same shared tree), and the cutover is what delivers true isolation — but in a legacy *multi*-world tree the resumed story (filtered by world_id) and the panels (global) can disagree. _(Codex P1 on the Slice 5 PR; inherent to pre-cutover legacy mode, resolved by setting `SENTINEL_WORLDS_ROOT`.)_
    - ✅ **Cross-process write locking (landed 2026-06-03, Path A / A1).** A per-world `filelock` (portable, cross-OS — no `fcntl`/`msvcrt` split) now guards every write: fs-manager `apply_world_update` (batch write + session-log append) and git-sync `commit_snapshot`/`teardown_world`/`rollback_to`/`init_world`. Both servers derive the **same** lock path for a world, so writes and commits serialize across processes. The lock file lives **outside** the world tree (`<WORLDS_ROOT>/.locks/<world_id>.lock`), so `teardown_world`'s rmtree can't delete a held lock — closing the teardown-racing-commit hazard. Shared mode (WORLDS_ROOT unset) collapses to one global lock (`<REPO_ROOT>/.sentinel-locks/shared.lock`), the correct granularity for the single shared repo. Lock held only for the disk/git op (sub-second), never across the LLM call; 15s fail-fast timeout → 503 (kept below the 30s dispatch HTTP timeout so a maxed-out wait surfaces as WORLD_BUSY, not a client read-timeout). Test: `tests/test_world_write_locking.py`. _Residual (deferred, not a blocker): the lock is per-operation, not held by the backend across the apply→commit span, so two concurrent turns on the **same** world could still interleave at that boundary — rare under ADR 0002's one-player-per-world model (the real concurrency is different worlds, which use independent locks). Backend-held cross-call locking would need a lock reachable across the Tailscale node split; revisit only if same-world concurrency becomes real._
      _Discovered: 2026-06-03 | Resolved: 2026-06-03 (A1) | Context: gemini-code-assist flagged on the Slice 2 PR; implemented with `filelock` per the cross-OS caveat._

- ◑ **Enforce + test the MCP network-isolation invariant (git-sync `rollback_to`/`list_snapshots` have no auth).** Both endpoints take `world_id` from the request body with no caller-identity binding, and `rollback_to` is a state-destroying op; once `SENTINEL_WORLDS_ROOT` is set, any caller who can reach git-sync:8012 can target an arbitrary world's repo. **Decision ([ADR 0003](adr/0003-access-gating-and-public-exposure.md), Accepted 2026-06-03):** resolve this by **network isolation, not endpoint auth** — the MCP servers stay bound to `127.0.0.1`/tailnet and are never on the public edge (Caddy only proxies `/api` + `/healthz`). **Landed (Path A/A2, 2026-06-03):** both servers default `--host 127.0.0.1` and **refuse an all-interfaces bind** (`0.0.0.0`/`::`) unless `SENTINEL_ALLOW_PUBLIC_BIND=1` (`_check_bind_host`); tested in `tests/test_mcp_bind_invariant.py`; `docs/WORKSPACE.md` documents that Caddy must never proxy `:8010`/`:8012`. Also landed: the **cutover config-agreement check** — the backend refuses to start in per-world mode unless both MCP `/health` report `worlds_root: true` (`backend/mcp_agreement.py`, `tests/backend/test_mcp_agreement.py`), closing the fs-manager-disagreement gap. **Remaining (optional defense-in-depth):** endpoint auth on git-sync's destructive ops — deferred; topology is the primary control per the ADR. The bind guard + Caddy-routing doc are the hard prerequisite and are now in place.
      _Discovered: 2026-06-03 | Updated: 2026-06-03 (A2) | Context: Slice 2 review swarm finding #1. Bind invariant + config-agreement check implemented; only optional git-sync endpoint auth remains._

- [ ] **Cutover agreement should verify the same `SENTINEL_WORLDS_ROOT` *value*, not just per-world presence.** `backend/mcp_agreement.py` confirms both MCP servers report `worlds_root: true`, which catches the common misconfig (one service per-world, another still shared) but **not** a backend pointed at `/a` while an MCP server uses `/b` — both report `true` and the check passes, yet writes/reads split across trees. Closing it needs `/health` to expose a root *identity* (the resolved path, or a digest) the backend can compare — a protocol change with symlink/mount-comparison fragility (a false mismatch would wrongly refuse a valid deploy), so deferred. Until then the same-root invariant is enforced operationally by Slice C's systemd units setting one env value for all three services.
      _Discovered: 2026-06-03 | Context: codex P1 on the A2 PR (#78). Triaged as a real residual but lower-risk than the presence gap A2 closed; the value-comparison protocol is its own small piece._

- [ ] **Per-tester scoping for `GET /api/worlds` (no cross-tester isolation today).** `list_worlds` returns *every* world on the server with no per-tester filtering — the closed-beta model has a single shared invite gate and **no accounts**, so the backend has no notion of "whose world this is." Multiple invited testers behind the one gate can therefore each enumerate all worlds' metadata (name, character, persona, turn count) and world_ids. This is **accepted for the closed beta** per ADR 0003's threat model (cost/abuse, not confidentiality; throwaway test data; the per-world token still gates *resuming* a world, so a leaked world_id alone can't open it) and is documented in `backend/routes/world.py::list_worlds`. **Fix when accounts land** (ADR 0003 § "Out of scope — vision", open-signup phase): scope the picker to the authenticated user's own worlds (capability tokens become things an account owns — see ADR 0003 forward-compat note). Flagged HIGH by gemini-code-assist on PR #74; triaged as ADR-accepted-not-a-blocker for the closed beta.
      _Discovered: 2026-06-03 | Context: PR #74 (ADR 0003 access layer) re-review. The "my worlds" picker is correctly "your worlds" for the single-operator closed beta; it becomes "everyone's worlds" only in a multi-tester deployment, which is the accounts/open-signup scenario ADR 0003 defers._

### Red-team findings — access/isolation audit (2026-06-04) — ✅ RESOLVED

All 8 confirmed findings from the construct-and-run red-team are fixed: the edge HIGHs (#1 `/api/sessions*` excluded from the public edge; #3 the `X-Forwarded-For`-spoofable rate-limit key) in PR #92; the fs-manager firewall cluster (#5/#6 protected-field smuggling; #2/#8 malformed-payload 500) in PR #93; the namespace out-of-band refactor (#7) in PR #94; and the provider-error leak (#4) in PR #92. The core token gate + traversal guards held throughout. Full triage: gitignored `scratch/review/redteam-2026-06-04-access.md`.

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

## Core Systems — Fantasy as Flagship Model

Sentinel's ambient surfaces (HP silhouette, tension meter, character cards,
encounter pressure) only mean something durable if the **systemic layer
underneath** is defined. Right now those surfaces visualize state the DM
emits freely — they read off `world_update` blocks with no rules attaching
mechanical meaning to the numbers. A "50/100 HP wounded silhouette" is
ambient feedback only; what 50 HP *does* (rests heal? potions? combat
damage curves? death stakes?) is invented turn-to-turn by the DM. That's
fine for ambience but fragile for cohesion.

**The flagship-genre approach (Russell 2026-06-12):** define the core
systems for the **Fantasy** genre first as the canonical reference model
— combat resolution, healing/recovery, magic costs and limits, encounter
mechanics, character progression, time/calendar advancement, weather and
environment effects, faction/economy basics, death stakes. Once Fantasy
has a coherent systemic layer, **other genres (Sci-Fi, Cyberpunk, Western,
Horror, etc.) follow the same shape**, swapping flavor (mana → energy →
ammo → ritual; healing potion → med-pack → bandage → spell) but inheriting
the structural pattern. This collapses N independent rulesets into "1
template + per-genre overrides," which is roughly how the world-creation
preset pipeline (`data/lore/core/presets/genres/`) already wants to work.

- [ ] **Define Fantasy-flagship core systems — the canonical mechanical
      layer underneath the ambient surfaces.** Big initiative; needs its
      own planning doc (probably `docs/CORE_SYSTEMS.md` with near-term /
      vision split per CLAUDE.md). Scope the v1 to "what's the minimum set
      of systems the DM and the schema need to agree on so a Fantasy run
      feels mechanically coherent?" Likely starting list:

      - **Combat resolution.** What does "attack" mean — initiative,
        hit/miss, damage curve, weapon type effects, defender's armor /
        stance. Today: the DM narrates outcomes freely; HP drops are
        ungrounded. Goal: a deterministic-enough resolution that the DM
        can describe but doesn't invent the *result* of (the systemic
        layer commits to outcomes; the DM dresses them).
      - **Healing & recovery.** How HP comes back — rest (short / long),
        healing items (potions, herbs, food), healing spells, time
        between encounters. Connects to the silhouette directly: today
        the DM picks "you regain 20 HP" arbitrarily; with a system, the
        rate is bounded and the silhouette's recovery is mechanically
        honest.
      - **Magic costs and limits.** Spell slots? Mana pool? Casting
        fatigue? Schools? Per-genre flavor will differ but the
        underlying "resource that gates magical action" pattern is
        universal — Fantasy mana ↔ Sci-Fi energy cell ↔ Cyberpunk RAM ↔
        Horror sanity. Defining the shape here once means every genre
        gets it for free.
      - **Encounter mechanics.** Tension's job is to *signal* an
        overdue encounter (PR #124); the core-systems layer says
        *what an encounter looks like* — surprise vs telegraphed,
        scaling to party level, escape conditions, persistent
        consequences. The new tension prompt clause names several
        encounter kinds (combat, crash, illness, trap, betrayal,
        weather) — those want light systemic frames.
      - **Character progression.** Levels? XP? Skill check
        improvement? Item-driven? Defining this commits to a power
        curve and lets the DM ground "you feel stronger" claims.
      - **Time & calendar.** Day counter already exists; needs
        meaning — what advances it (sleep, travel, encounters)?
        What changes when day N → N+1 (NPC routines, faction
        movements, weather)?
      - **Weather & environment.** Already tracked in `world.weather`
        + `world.timeOfDay`; needs mechanical hooks (rain → reduced
        tracking, night → stealth bonus, sandstorm → visibility
        penalty).
      - **Faction & economy basics.** Reputation tracking, basic
        currency, trade. Even a minimal version (`gold` + `reputation
        per faction`) gives the DM real stakes to play with.
      - **Death stakes.** What HP=0 actually means — unconscious
        with a save, permadeath (the existing `permadeath` flag on
        sessions hints at this), reincarnation, run-ends. The
        silhouette's "Fallen" state needs a system to resolve.

      **Approach:** start with a planning doc (one Russell-input session
      to set the shape) → draft Fantasy v1 spec → pilot one system end-
      to-end (combat is the obvious candidate — high-stakes, the player
      will *feel* the difference between systemic and improv) → wire
      DM-prompt schema additions + Fact-Extractor handling → add the
      first 2–3 genre overrides (Sci-Fi + Cyberpunk are good early
      proofs that the template generalizes).

      **Why now:** the ambient surfaces shipping this month (tension,
      HP silhouette, action suggestions) are starting to *imply* a
      systemic layer that doesn't exist yet. Each surface we add
      without grounding it widens the gap between what testers see and
      what the world actually models. The silhouette in particular
      will surface this — when HP drops dramatically the player will
      ask "how do I heal?" and the DM will improvise an answer that
      contradicts the next session's improvisation.

      **Cross-links:** [[project_minimum_viable_structure_loop]] —
      this initiative is the concrete version of the "minimum viable
      structure" research thread; we're committing to *find* that
      minimum by building it. Also lines up with the existing
      "Player action catalog" item above (item 6 of which already
      names Fantasy combat as the proof-of-concept) — the action
      catalog is one slice of the core systems.

      _Discovered: 2026-06-12 | Context: Russell asked for this while
      drafting the player-vitals HP silhouette PR — surfacing HP
      ambiently raised the question "but what does HP *mean*?". The
      flagship-genre framing (Fantasy first, other genres pattern on
      it) was his explicit call, replacing an N-independent-genres
      approach with 1-template-plus-overrides._

- [ ] **Author race-specific silhouette geometries for `PlayerVitals`.**
      The dispatch landed in PR #129 (Russell 2026-06-12 "put a stub out
      for different races"): `apps/sentinel-ui/src/components/world-state/
      PlayerVitals.jsx` has a `RACE_BODIES` map keyed by race that all
      Fantasy entries currently point at the shared `HUMAN_BODY_PATH`. The
      plumbing is real (reads `player.race` from the DM-emitted character
      record, looks up case-insensitively, falls back to human for unknown
      races), but every elf / dwarf / orc renders as a human-shaped figure
      today. This is the **content** half — author distinct SVG path
      strings per race so each one reads visually distinct.

      **v1 set (Fantasy flagship, ordered by player frequency):**
        1. dwarf — shorter, broader torso, stubbier legs
        2. elf — taller, leaner, longer limbs
        3. halfling — smaller overall, head-to-body ratio closer to a child
        4. orc / half-orc — broad shoulders, hunched, heavier limbs
        5. dragonborn — taller, tail hint, broader chest
        6. tiefling — close to human with horns hint at the head silhouette
        7. gnome — small, slight, head proportion smaller than halfling
        8. half-elf — slight elf lean, mostly human geometry

      Once Fantasy has its set, the other genres' equivalents stub in via
      the same map (Sci-Fi: human / android / synth / alien-bipedal;
      Cyberpunk: meat / chromed / rigger; Western: mostly humans;
      Horror: human / cursed-variant). The map structure is genre-agnostic
      — only the keys change per genre — so once each path constant is
      authored, registration is one line.

      **Constraints inherited from the existing component:**
      - 100×180 viewBox; head ellipse stays a separate `<ellipse>` element
        so the head proportion is consistent across races (unless we
        deliberately vary it, e.g. dragonborn). All-in-one path is fine
        too — just clip-path needs to cover the whole figure.
      - Path must close cleanly (the damage wash is clipped to it; a
        non-closed shape lets the wash escape).
      - Stay stroke-only on the visible render (no fill); the wash
        provides the only fill. Single-color stroke against the
        codex-ink palette.
      - Keep the proportions visually distinct enough that a player
        glancing at the panel can tell "I'm playing a dwarf" without
        reading the character name.

      **Acceptance per race:** new path string at the top of
      `PlayerVitals.jsx`, registered in `RACE_BODIES` under the
      lowercased race name, screenshot in the PR body so the visual
      change is reviewable. No new tests needed — the existing
      `renders identical geometry across all stubbed races` test
      becomes the canary that gets retired naturally as paths diverge.

      Cross-links: builds on the [[project_entity_sweeper_direction]]
      and the Core Systems section above; the silhouette ↔ race
      pairing is one slice of the broader "what does the systemic
      layer underneath a character look like?" question.
      _Discovered: 2026-06-12 | Context: stub landed in PR #129 with the
      dispatch mechanism + the case-insensitive lookup; per-race art was
      explicitly deferred so individual races can land race-by-race
      without re-architecting the component._

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

- [ ] **Expand `apps/sentinel-ui/` test coverage to stores and the stream hook.** vitest + @testing-library/react infrastructure landed and now covers ~61 tests across 10 files (`utils/delta.js`, the `EntityCard` + `DeltaMessage` primitives, the `useWorldHydration` hook, and components `AppShell`, `WorldList`, `DataBrowser`, `TopBar`, `StatusIndicator`, `PanelRouter`). The next slice is the Zustand stores (`chatStore`, `worldStore`, `uiStore`, `personaStore`) and the `useDMStream` hook — the latter is the trickiest because it touches `fetch` and the SSE event parser, but it's also the highest value for catching turn-loop regressions. Tests should mock `fetch` with a small SSE-event-emitting fake. Defer until either a regression makes one of these load-bearing or someone wants to spend a focused session expanding coverage. See `docs/TESTING.md` "Near-term test work" for the full framing.
      _Discovered: 2026-03-26 | Updated: 2026-04-15 | Context: original "no frontend tests" gap closed by the vitest infrastructure PR; this is the followup item for the rest of the surface_



- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_

- [ ] **`install`/`install-backend` use bare `pip`, breaking on PEP 668 without an activated venv.** `just install` and `just install-backend` call `pip install -r …` bare, which only works if a Python env with write access is already on `PATH`. On a stock Ubuntu 24.04 (Python 3.12, marked PEP 668 externally-managed) there's no venv and bare `pip install` is refused, so a fresh or post-reboot backend setup fails until someone manually creates a venv. As of 2026-06-02 the dev backend on origin-core runs from a manually-created `.venv/` at repo root. **`just dev-backend` is fixed (2026-06-04):** a `venv_python` justfile var autodetects the repo-root `.venv` (cross-OS `.venv/bin` vs `.venv/Scripts`, PYTHON_BIN override wins, falls back to system python) and runs `… -m uvicorn`, so it works without manual activation. The remaining work is the install side: have `install`/`install-backend` create/use `.venv` (e.g. `python -m venv .venv` then install into it) so a fresh clone is runnable without a manual venv step. Pairs with the requirements-manifest item above.
      _Discovered: 2026-06-02 | Context: surfaced while bringing the backend up on origin-core for the tailnet dev site after a reboot — no venv existed and PEP 668 blocked system pip. dev-backend half resolved 2026-06-04 while restarting the stack on Groq from a non-activated shell._

- [ ] **`.env` precedence disagrees between the backend and `start-cloud.sh`.** The backend loads `infrastructure/.env` with `load_dotenv(override=False)` (shell env wins), while `scripts/start-cloud.sh` does `set -a; source infrastructure/.env; set +a` (the `.env` file wins, clobbering any value already exported into the environment). They reach the same result today because nothing pre-exports these vars, but the semantics are opposite — an operator who `export`s e.g. `SENTINEL_WORLDS_ROOT` before `just start` would find it silently overridden by the (possibly blank) `.env` line for the MCP servers but honored by the backend. Pick one precedence (env-wins, mirroring the backend, is the conventional one) and make both paths agree.
      _Discovered: 2026-06-05 | Context: found while documenting the local per-world dev split — it's why a `SENTINEL_WORLDS_ROOT=… just start` launcher can't work without also touching `.env`._

- [ ] **`just fs-manager` / `just git-sync` don't load `infrastructure/.env`.** Only the `just start` path (`scripts/start-cloud.sh`) sources `.env` into the MCP server processes; the individual dev recipes run `server.py` directly, and the servers themselves only read `os.environ` (no `load_dotenv`). So setting `SENTINEL_WORLDS_ROOT` (or any `SENTINEL_*` knob) in `.env` and then starting a server via its individual recipe yields shared mode — and, paired with a per-world backend, trips the `mcp_agreement` startup refusal with a confusing "services disagree" error. Fix: have the MCP servers load `infrastructure/.env` themselves (symmetric with `backend/config.py`, and it would also fix the precedence item above by giving all three the same loader), or document the limitation in the recipe comments.
      _Discovered: 2026-06-05 | Context: found while documenting the local per-world dev split; the WORKSPACE.md recipe relies on the shell env (which these recipes inherit) rather than `.env`._

- [ ] **`just env` / `just start` overwrite a hand-set `OPENAI_API_KEY` with the template placeholder.** The chezmoi template ships `OPENAI_API_KEY=gsk_your-groq-key-here` as a literal placeholder (no secret/`env` template function), so `chezmoi apply --force` — run by `just env` and as the `env` prerequisite of `just start` — regenerates `infrastructure/.env` and clobbers a real key configured by hand. In practice this makes `just start` unusable once a real key is in `.env` (it silently reverts to the placeholder, and the backend then fails to auth against Groq), which is why the dev `.env` is maintained by hand and `just env` is avoided after the first render. Fix: source the key from a chezmoi secret or an `env` passthrough (e.g. `OPENAI_API_KEY={{ env "OPENAI_API_KEY" }}`) so regeneration preserves a real value. Pairs with the two `.env`-loading footguns above and the per-world local-dev recipe in `docs/WORKSPACE.md`.
      _Discovered: 2026-06-05 | Context: found while verifying review feedback on the local per-world dev docs (#96) — both bots flagged that `just start`'s `env` prerequisite wipes a direct `.env` edit; the same regen also wipes the Groq key, which is why the recipe uses the shell env and the individual server recipes instead._

- [ ] **Record `load-smoke` baselines before opening the closed alpha.** `scripts/load-smoke.py` / `just load-smoke` exists (see `docs/TESTING.md` § "Load smoke"); now run it against the prod-like stack and capture a baseline so future regressions surface. Suggested matrix: N=2/5/10 concurrent worlds × M=3 turns × `--warmup 1`, against the prod-LiteLLM-fronted backend on the new droplet. Record p50/p95/p99 first-token + total-turn + error rate per N, plus the LLM provider headroom that step is operating under. Stick the numbers in this BACKLOG entry as a "Last measured" line so anyone running it later has the prior baseline to diff against. **Trigger:** part of the public cutover (A4) checklist, immediately after `just cutover-check` reports READY and before the Caddy gate goes live.
      _Discovered: 2026-06-05 | Context: spawned from the closed-beta readiness verification — the suite has zero load tests today, only correctness-under-concurrency (tracer-soak), so the "≤10 concurrent users" target is a planning input not a measurement. Capturing real numbers turns it into one._
      _First-run finding (2026-06-05, against the live origin-core stack on Groq dev tier): **2 concurrent worlds × 2 measured turns × 1 warmup (6 LLM calls in ~53s) hit Groq's per-org TPM 429 rate-limit on 2 of 4 measured turns** — verdict ❌ broken. The script worked correctly; the LLM provider is the binding constraint, which confirms the readiness report's call to front prod with a paid LiteLLM tier (see [[project_prod_topology_closed_alpha]] memory note). Re-baseline against the prod LiteLLM proxy once the prod droplet is up._
      _**First paid-LLM baseline (2026-06-06): ✅ healthy via LiteLLM proxy → Gemini 2.5 Flash.** Groq's Developer tier was unavailable ("Developer tier upgrades are temporarily unavailable due to high demand"), pivoted to Gemini Flash via the existing origin-core LiteLLM container (route `dm-sentinel` → `openai/gemini-2.5-flash` against `https://generativelanguage.googleapis.com/v1beta/openai`). Scaled up from the free-Groq probe (which was deliberately N=2 × M=2 to find the rate-limit floor) to a proper baseline: **N=5 worlds × M=3 turns × 1 warmup = 20 LLM calls in 36.5s wall-clock, 15/15 turns succeeded, 0 errors, 0 429s.** Numbers (warm path): world provisioning p50=10.24s p95=14.35s (DM intro is the heavy call); first-token p50=3.31s p95=6.22s; total-turn p50=5.23s p95=8.44s. Slightly slower than Groq's ~4s/turn dev experience but well under the script's `_FIRST_TOKEN_P95_DEGRADED_S=8.0` and `_TOTAL_TURN_P95_DEGRADED_S=15.0` thresholds. Architecture validated end-to-end. **Side finding (operational):** the two MCP servers (fs-manager + git-sync) had been running the same Python processes since 2026-06-02 — predating PR #94's namespace-via-query-param fix — so the first attempt failed with `NAMESPACE_VIOLATION` 403s until both servers were restarted. **MCP servers carry stale code across multi-day uptimes when started via `nohup` rather than systemd.** ADR 0003 Slice C systemd templates (`infrastructure/systemd/sentinel-fs-manager.service`, `infrastructure/systemd/sentinel-git-sync.service`) are the durable fix; they pick up code on `systemctl restart` and survive reboots._
      _**N=10 concurrency baseline (2026-06-06): ⚠ degraded but functionally clean via the same LiteLLM/Gemini Flash path.** Same scenario at peak alpha concurrency target: **10 worlds × 3 turns × 1 warmup = 40 LLM calls in 43.6s wall-clock, 30/30 turns succeeded, 0 errors, 0 429s.** Provisioning p50=9.84s p95=10.94s (slightly better than N=5 — likely Google load-balancer variance evening out across more samples). First-token p50=3.66s **p95=10.86s** p99=11.25s; total-turn p50=6.27s p95=11.20s p99=11.66s. First-token p95 (10.86s) tripped the script's 8.0s placeholder threshold → ⚠ degraded; total-turn p95 (11.20s) stayed under 15s. **Architecturally sound:** p50 barely shifted from N=5 to N=10 (+10% on first-token); p95 grew 74%, attributable to Gemini Flash latency variance under concurrent load (Google-side LB routing variability, not sentinel). Bounded p99 (11.25s) means no individual turn pathological. **Decision deferred to Russell:** (a) accept current envelope (most turns under user-noticeable threshold, worst case bounded), (b) recalibrate script's degraded threshold from 8s placeholder to ~12s warm-path-at-10 reality, (c) try Gemini Flash-Lite if cost-or-speed wants probing. For closed alpha at planning target 10 concurrent / 2.5 average: **green-light at current envelope**._

- [ ] **Adopt file-observer's `provenance` vector for exported training datasets.** When `just export-training-data` (via `scripts/export_training_data.py`) writes the chatlog corpus, also run `fo` against the script's actual chatlog output dir and stash the manifest alongside. The export script accepts `--out <dir>` (defaults to `<root>/datasets`) and writes chatlogs to `<out>/chatlogs/` — implementation should pull the resolved path from the export step rather than hardcoding `datasets/chatlogs/`, since the configurable output dir can change (caught by gemini-code-assist on the PR that filed this item). File-observer's per-corpus `provenance` vector (v1.6+) aggregates which models / toolchains / authors produced what content — useful dataset-honesty annotation when the alpha corpus is shared externally (per [[project_minimum_viable_structure_loop]]). Low effort: extend `just export-training-data` to invoke `fo "<out>/chatlogs/" > "<out>/manifest.json"` post-export, where `<out>` is whatever the script resolved. **Trigger:** when alpha generates real corpus worth labeling (probably post-cutover). See `/srv/projects/pkplab/scanner/` for file-observer source. Cross-link: [[project_chatlog_home]] for the substrate distinction.
      _Discovered: 2026-06-06 | Context: surveyed Scanner's tree (`/srv/projects/pkplab/scanner`) after the file-observer v1.11 announcement and identified this as a Tier-1 modest-value adoption that doesn't need new code on Scanner's side, just consumption of an existing capability._

- [ ] **Borrow the `corpus_sweep.py` empirical-regression pattern to defend `datasets/chatlogs/` health.** Scanner has `scratch/review/corpus_sweep.py` + `audit.sh` — scans the real corpus, diffs against a frozen `sweep_baseline.json`, exits non-zero on regression; `--update` re-baselines after intentional change. **Sentinel-applied:** if `backend/datasets.py::build_chatlog` ever silently stops emitting file-observer-detectable speaker-labeled output (regex shift, escape bug, schema drift on Scanner's side), a frozen baseline run as part of `just check` would catch it before testers see it. Effort: ~50 lines of Python wrapping `fo` against a small sample corpus + a one-time baseline file. **Trigger:** post-cutover, once alpha corpus has enough body to be worth defending. **Important coordination point:** `backend/datasets.py` mirrors `file_observer.scanner.CHATLOG_SPEAKER_LABEL_RE` (schema 1.3) as a soft external contract — Scanner Claude's `project_sentinel_corpus_layout` memo records this on their side, mine records it in [[project_chatlog_home]]. Either side changing the regex routes through Russell first. See `/srv/projects/pkplab/scanner/scratch/review/README.md` for the original pattern.
      _Discovered: 2026-06-06 | Context: same Scanner-tree survey as the provenance-vector item above; this is a discipline-borrow, not a code-share — adapting their empirical-regression pattern to defend our own export pipeline._

- [ ] **Install ADR 0003 Slice C systemd units for the MCP servers on origin-core (dev box, not just prod droplet).** The unit templates already exist at `infrastructure/systemd/sentinel-fs-manager.service` and `infrastructure/systemd/sentinel-git-sync.service` (landed PR #80, Slice C). They were designed for the prod droplet, but origin-core dev would benefit from the same: today, `just fs-manager` / `just git-sync` start the servers via `nohup` (or just run in the foreground), and once a process is up it stays up across reboots only by accident — and worse, **it doesn't pick up new code without an explicit kill+restart**. This bit us 2026-06-06: both MCP processes had been running since 2026-06-02 with code that predated PR #94's namespace-via-query-param fix, causing the first paid-LLM load-smoke baseline run to fail with `NAMESPACE_VIOLATION` 403s until both were manually killed and restarted. **Fix:** copy the unit templates into `/etc/systemd/system/` on origin-core (with `<REPO_ROOT>` substituted), `systemctl daemon-reload && systemctl enable --now sentinel-fs-manager sentinel-git-sync`. After that, `systemctl restart sentinel-{fs-manager,git-sync}` picks up code on demand and they survive reboots. Operational consideration: if/when the MCP servers move to per-world mode (`SENTINEL_WORLDS_ROOT` cutover), the systemd units' `EnvironmentFile=` arrangement already handles it — same units, just different env values. The closed-alpha cutover should set this up anyway; doing it on origin-core dev now is a dress-rehearsal that catches operational gaps before they bite under invited-tester load.
      _Discovered: 2026-06-06 | Context: stale MCP processes (3+ days uptime, started via nohup) carried pre-PR-#94 code in memory and rejected the first paid-LLM load-smoke baseline run. Documented in the "Record load-smoke baselines" BACKLOG entry's 2026-06-06 stamp; this item is the durable fix._

- [ ] **Consider queueing instead of hard-reject for `SENTINEL_MAX_CONCURRENT_STREAMS` if alpha testers find the 503 jarring.** The 2026-06-06 design landed hard-reject (503 + `Retry-After: 5`) when at concurrency cap — explicit choice over queueing, per Russell. Rationale: simpler to reason about, predictable blast radius, the "Sentinel is busy" UX is fine for a ~10-person closed alpha cohort. **Trigger to revisit:** if alpha telemetry shows non-trivial 503 noise (e.g. >5% of `/api/stream` requests rejected on a typical session) AND testers report it disrupts play, build a small queue layer: bounded FIFO with timeout + fairness; tester sees a "Sentinel is busy — retrying" toast on the SPA side while the queued request waits. Effort estimate when triggered: ~1 day of backend + frontend work. Don't pre-empt without evidence.
      _Discovered: 2026-06-06 | Context: filed at the same time as PR feat/max-concurrent-streams — closed-alpha blocker that Russell decided "hard-reject only" for v1. Captured as the natural follow-up so future-me doesn't re-derive when (if) the 503 noise gets reported._

- [x] **Drop the abandoned `5514960f` session orphan from `data/state/core/*` + `data/lore/core/sessions/`.** ✅ **RESOLVED 2026-06-07 by PR #110 (`376bbbd`).** PR #108's squash-merge brought five files into `master` from gameplay traffic that landed on the feature branch during the live alpha window: `data/state/core/sessions/5514960f-…json`, `data/lore/core/sessions/5514960f-…md`, `data/state/core/entities/russalo.json`, `data/state/core/entities/warden_meral_hult.json`, `data/state/core/items/warden_s_ledger.json` — plus a `data/state/core/world/state.json` mutation (`tension: 6` → `7`, same `"Thornwatch forest edge"` location both sides). After the 2026-06-07 closed-alpha cutover armed per-world isolation (`SENTINEL_WORLDS_ROOT=<WORLDS_ROOT>`), the backend no longer reads from the shared `data/` tree in any deployment; these files were dead detritus cluttering master. The sibling session `4f1cebed` was migrated to a per-world repo during the cutover and `git reset --hard origin/master` dropped its files; `5514960f` couldn't be reset that way because it was already in origin/master via the squash-merge — PR #110 did the deletion directly. Reverted `data/state/core/world/state.json` to its pre-PR-#108 value (`tension: 6`) via `git checkout a830fd9 -- …`. **NOT dropped (still potentially seed/example data):** `data/state/core/entities/{briarfolk_messenger,chez,mir_halder,pell_family,sal,ser_denna}.json`, `data/state/core/items/bruise-wax_letter.json`, the older lore session markdowns `13517ab7-…` and `6f9a9071-…` — these predate the alpha window. **Generalizable pattern:** when a squash-merge captures gameplay-state mutations alongside intended code changes (because gameplay was happening on the feature branch during PR review), the gameplay data lands permanently on master. Two preventatives: (a) keep `SENTINEL_WORLDS_ROOT` armed in any environment that's also doing PR development (so gameplay never touches the code repo's `data/`); (b) check `git status -b --short` on a feature branch before opening a PR — a per-turn `[sentinel] world=… session=… turn=…` commit appearing locally is the early-warning signal.
      _Discovered + resolved: 2026-06-07 | Context: surfaced during the closed-alpha cutover restart; the 5514960f world is unreachable post-cutover and the data files were ghost detritus on master. Filed and resolved same-day via PR #110._

- [x] **Token re-issuance plan for Johnny Bananna's session 4f1cebed (world fa0ec595).** ✅ **RESOLVED 2026-06-07.** During the cutover restart, the previously-anonymous `SENTINEL_SESSION_TOKEN_SECRET` was set to a fresh 48-byte secret, so any world-session token in a tester's SPA localStorage no longer validated (HMAC keys on the new secret). The fa0ec595 world data was migrated to a per-world repo (preserved on disk), but a returning tester hit `GET /api/world/fa0ec595-…` with a stale token → 401 + `"missing world session token"`. Initial choice was wait-and-see (option iii); when Johnny pinged with "API error could not load world," the trigger fired and we executed option (ii): minted a fresh 7-day token via `backend.auth.world_token.mint(world_id, secret=…, ttl_seconds=7*24*3600)` using the live secret, smoke-tested it against `GET /api/world/fa0ec595-…` (200 with full hydration) and verified the token-binds-to-world constraint by trying it against a different UUID (403). Relayed to Russell with paste-into-localStorage instructions for Johnny: key `sentinel.worldToken.fa0ec595-37b5-41b0-a4ff-3f8d176a0047` (dots, not dashes — my earlier draft of this entry had the prefix wrong; the SPA's `KEY_PREFIX = 'sentinel.worldToken.'`). **Generalizable mechanism for any future tester-after-secret-rotation case** — same Python one-liner against `backend.auth.world_token.mint` works; the gotchas are (a) the localStorage key prefix is `sentinel.worldToken.<world_id>` (dots), and (b) verify the token works for the right world AND fails for a wrong world before relaying (catches a secret-misread on the mint side). Don't bake this into a backend endpoint without thinking about the auth on THAT endpoint — minting bypasses the per-world token check by definition, so an unauthenticated "give me a token for any world" route would be its own access-layer hole.
      _Discovered + resolved: 2026-06-07 | Context: surfaced during cutover-restart token-rotation analysis (data preserved via per-world migration, but pre-secret tokens no longer validated); resolved later same day when Johnny actually returned and hit the 401, triggering option (ii) execution. Kept as a post-mortem entry because the mechanism + gotchas (localStorage key shape, mint-side smoke before relay, future-endpoint auth concern) will recur on any secret rotation._

- [ ] **`SENTINEL_TRUSTED_PROXY_HOPS` chezmoi-clobber durable solution.** `infrastructure/.env` on origin-core has the cutover-armed value `SENTINEL_TRUSTED_PROXY_HOPS=1` (required for the gate-fronted X-Forwarded-For semantics — see [[project_gate_fronted_topology]] memory). The hand-maintained header on this `.env` notes it should normally be chezmoi-generated; if someone reinstates `just env` here (chezmoi regenerates from `.chezmoi/dot_infrastructure/dot_env.tmpl`) without first migrating this value into a per-host conditional, the value clobbers back to `=0` and the per-IP rate-limiter starts keying on gate's IP (one shared bucket for every alpha tester). **Proposed solution (option a' from the 2026-06-07 cutover discussion):** add a chezmoi data variable (e.g. `{{ .sentinel.trusted_proxy_hops | default 0 }}`) and configure origin-core's chezmoi data file to set the value to 1. Other hosts default to 0 (safe — no proxy in front means socket-peer is correct). Same shape as how `chezmoi.os` already gets used elsewhere in the template. Don't default the template to `=1` outright — that would re-introduce the XFF spoofability fix from red-team #3 / PR #92 on every dev box that lacks a trusted proxy. **Trigger:** when chezmoi is reinstalled on origin-core (the `.env` header notes it's currently absent), OR when the per-host config story comes up for any other knob (e.g. `SENTINEL_WORLDS_ROOT`'s per-host path). Same approach generalizes.
      _Discovered: 2026-06-07 | Context: cutover-restart confirmed origin-core has no chezmoi today (so the clobber risk is hypothetical here), but the value's load-bearing role means future chezmoi reinstall must not silently revert it. Filed durable rather than hoping nobody runs `just env`._

- [ ] **Re-enable DM action-pill tones with a player-visible legend.** PR #112 shipped a 5-tone color palette for DM-emitted action pills (aggressive=rust, defensive=cobalt, clever=amber, curious=moss, cautious=ether). 2026-06-07 UX call dropped the tone-rendering for v1 — all DM pills now render in a single amber color matching the inline `<action>` highlights — because color meaning wasn't conveyed to the player (no legend, no tooltip) and DM tone-assignment can be inconsistent ("clever" vs "curious" is a judgment call). The `tone` field is STILL ingested + persisted in the `world_update` block (engine + schema + frontend store all keep it round-tripping), the DM prompt still emits tones, and the test suite still validates the data flow. The render-side fix at `apps/sentinel-ui/src/components/shell/ActionPillRail.jsx` is the only place that ignores tone today (`DM_PILL_CLASS` constant). **When the time comes:** restore the `TONE_CLASSES` map + `classFor()` helper (PR #113's history has the original — pre-2026-06-07), AND add a player-visible legend so tones mean something: a small key on long-press / hover, OR a one-time intro tooltip, OR a settings-panel cheatsheet. Without the legend, the rainbow reads as noise. Effort when triggered: ~30 min for the render swap + ~1-2 hr for whichever legend shape gets picked. **Trigger:** when there's a deliberate UX moment to teach the tone semantics (alpha cohort feedback says they want it, or a tutorial sequence lands that can introduce them inline).
      _Discovered: 2026-06-07 | Context: dropped during the first live-alpha smoke of the action-suggestions feature; Russell explicitly asked to defer-with-note rather than rip the data structure out._

- [ ] **iOS stuck `:hover` on action pills after tap.** Tailwind's `hover:` variant doesn't gate on `@media (hover: hover)`, so iOS Chrome / Safari trigger the hover background fill on touch and leave it lit until the next tap somewhere else. Visible in `ActionPillRail.jsx` (`hover:bg-amber/10`, `hover:bg-codex` on the pill classes) and `NarrativeText.jsx` (inline action button's `hover:` classes). Cosmetic only — functionality is unaffected. **Fix shape (when triggered):** sweep all `hover:` usages in `apps/sentinel-ui/src/components/` and wrap them in a hover-capable-media-query Tailwind variant. The canonical patterns: either a custom variant in `tailwind.config.js` (`addVariant('hover-hover', '@media (hover: hover) { &:hover }')`) used as `hover-hover:bg-amber/10`, OR an `onTouchEnd` handler that blurs the element to clear the stuck state. Tailwind v3.4+ added `pointer-fine:` / `pointer-coarse:` variants that work too but require Tailwind upgrade if not already there. **Trigger:** at the next iOS-polish pass that catches all hover usages in one swing — single-spot fixes will leave other spots stuck.
      _Discovered: 2026-06-07 | Context: surfaced on the live alpha when Russell observed the first DM pill stayed filled-in after tapping. Cosmetic but ubiquitous on iOS — worth a single sweep rather than playing whack-a-mole as more `hover:` usages get added._

- [ ] **DM-narrative markdown emphasis renders ONLY on the live streamBuffer, not on committed messages.** PR #113 added `*x*` / `**x**` / `***x***` → `<em>` / `<strong>` / `<strong><em>` rendering in `apps/sentinel-ui/src/components/narrative/NarrativeText.jsx`. Verified working when the DM is mid-streaming a turn (visible italic on the caret/cursor line). After the turn commits — content moves from `streamBuffer` → `messages[]` and re-renders via the same `<NarrativeText>{msg.content}</NarrativeText>` path — the emphasis disappears and asterisks render literally. Bold is missing across the board (no `<strong>` visible anywhere; possibly the DM hasn't emitted any `**bold**` yet but the parser is supposed to handle it when present). Both paths flow through the same component with the same wrapper classes (`text-ink font-crimson leading-relaxed prose-narrative`); on paper they should produce identical output. Hypotheses to investigate: (a) `commitStreamMessage` / `stripWorldUpdate` may be normalizing or escaping the asterisks before they land in `messages[]` (regex doesn't appear to touch them, but worth a runtime trace); (b) a stale React tree / closure where the committed-message branch in `NarrativeScroll.jsx` re-renders with an old reference; (c) the `prose-narrative` CSS class might be hitting `<em>`/`<strong>` differently when wrapped by a `<div>` vs adjacent to a `<span class="cursor">` (the streaming path has the cursor span); (d) parseActionTags is returning subtly different segments for the two inputs. Acceptable workaround for now: live-streaming italics + amber inline action highlights are working, and committed plain text reads cleanly (asterisks visible but minor). **Trigger to fix:** when collecting alpha-tester feedback flags this as confusing, OR when adding any other text-formatting work to the same render path.
      _Discovered: 2026-06-07 | Context: Russell's live alpha check after PR #113 merged — "The only formatting I see inline is italics on the caret line and the amber inline action options at the end. No italics or bold in main DM chat body, no bold anywhere." Confirmed deployed bundle (BtGeQSxG.js) DOES contain the bold/strong code (`font-bold` strings present, regex patterns in place), so the divergence is at render-time, not deploy. Diagnostic deferred to keep momentum toward feedback collection._

- [ ] **Player font-size control via Settings drawer.** Tester feedback during the 2026-06-07 alpha smoke: narrative font is too small for comfortable reading on iOS. Need an in-product control. **Approved shape (Russell, 2026-06-07):** open as a "Settings" drawer/sheet from a gear icon in the TopBar (NOT inline controls in the TopBar itself — keep that chrome clean; the drawer is the future home for theme, density, audio, and other player prefs as they accumulate). First setting in the drawer is font-size, 4 steps: `small | normal | large | xlarge` mapped to Tailwind `text-sm` / `text-base` / `text-lg` / `text-xl`. Controls: A− / A+ pair button with current size hint; greyed-out at min/max. **State:** new `apps/sentinel-ui/src/stores/uiStore.js` with `fontSize` enum, persisted via `zustand/middleware/persist` to localStorage so it survives refresh. **Scope of application:** narrative wrapper (`text-ink font-crimson ...`) in `NarrativeScroll.jsx` — both committed DM messages AND live streamBuffer. Does NOT scale the pill rail, system log entries, command bar, or UI chrome (those stay at chrome scale for legibility / hit-target reasons). **Files affected:** new `stores/uiStore.js`, new `components/shell/SettingsDrawer.jsx`, modified `components/shell/TopBar.jsx` (add gear icon), modified `components/narrative/NarrativeScroll.jsx` (subscribe to fontSize, apply Tailwind class to narrative wrappers). Tests: store unit tests (clamp + persist), drawer component tests (button cycling, persistence survives unmount/remount). **Deploy window agreed:** Monday 2026-06-08, 05:00–08:00 PST — Russell's preferred restart-window. SPA-only change → zero downtime expected for the deploy itself; the early-morning slot is the safest default for any rare tester impact (lowest-traffic window for a closed-alpha cohort on PST).
      _Discovered: 2026-06-07 | Context: tester reading the live alpha on iOS Chrome flagged the font as too small; Russell agreed on the Settings-drawer shape (option b from the proposal) rather than always-visible TopBar controls. Implementation planned for tomorrow AM._

- [x] **In-product feedback form at `/alpha/feedback/`.** ✅ **SHIPPED 2026-06-07 via PR #116** (one day ahead of the originally-targeted Monday window — Russell confirmed the brief restart envelope was acceptable + the value of structured tester reports outweighed waiting). Live smoke confirmed: form submission lands as JSON at `/srv/projects/project-sentinel/feedback/YYYY-MM-DD/`, with full auto-capture working (worldId/sessionId null when submitting from /feedback route, viewport + currentUrl + UA + clientIp populated). One small follow-up filed: `VITE_BUNDLE_HASH` build-time injection isn't wired up — the on-disk `bundleHash` field is literally `'dev'` until that lands. Doesn't break anything; just loses the "which bundle was the tester on?" provenance. — Russell 2026-06-07: "1st useful item would be to create sentinel.russalo.com/alpha/feedback/ with a link on the top bar." Replaces ad-hoc feedback channels with a structured submission path that auto-captures context, so triage into `docs/ALPHA_FEEDBACK.md` + `docs/BACKLOG.md` doesn't need a back-and-forth to nail down the tester's platform / browser / world. **Route:** `/alpha/feedback` (Wouter route in `App.jsx`). **TopBar link:** small Feedback link (chat-bubble or megaphone icon) next to existing TopBar status. **User-entered fields:** Subject (≤140 chars), Body (≤4000 chars), Category (Bug / UI-UX / General / Feature — radio matching `ALPHA_FEEDBACK.md`'s sections), Platform (free-text — iOS, Windows 11, macOS, etc.), Browser (free-text), Severity (low/medium/high, optional), Reproducible (yes/no/sometimes, optional), Email-or-handle (optional, for follow-up). **Auto-captured fields:** worldId + sessionId (from `playerStore` when populated — null otherwise; null is informative — distinguishes "in-session feedback" from "pre-session feedback / can't get in"), submittedAt (server-side), userAgent (server reads request header), viewport `${window.innerWidth}x${window.innerHeight}`, currentUrl (full URL minus any token query params), bundleHash (build-time constant for SPA version provenance). **Screenshot upload deferred to v2** (blob handling complexity not justified for first cut). **Auth shape:** per-world token NOT required (testers may need to report inability to enter a session); basic_auth at the Caddy edge is sufficient. **Rate limit:** new env knob `SENTINEL_RL_FEEDBACK_PER_HOUR=10` via the existing per-IP `RateLimiter` infrastructure — generous for legitimate use, caps abuse. **Storage:** JSON files at `/srv/projects/project-sentinel/feedback/YYYY-MM-DD/<timestamp>-<short-id>.json` — top-level repo dir, **gitignored** (must add `/feedback/` to `.gitignore` — same lesson as the 2026-06-07 cutover, do NOT pollute the code repo). New env knob `SENTINEL_FEEDBACK_ROOT` with that as the default, allowing override. Append-only — no edits/deletes via API. **Backend:** new `backend/routes/feedback.py` exposing `POST /api/feedback` with field validation (length limits, category enum), per-IP rate-limit, atomic-write to disk. **Frontend:** new `pages/Feedback.jsx` with form state + submit handler. Success state shows a confirmation + back-to-game link (does NOT auto-redirect). Failure state shows the error inline. **Caddy edge:** `/api/feedback` is already gated inside the existing `handle /api/*` block — no new edge config. **Operational flow:** I tail / read from `<SENTINEL_FEEDBACK_ROOT>` periodically and graduate items into `docs/ALPHA_FEEDBACK.md` + `docs/BACKLOG.md`. The on-disk JSON is the raw stream; the docs are the human-curated view. **Tests:** backend POST validation (required fields, length limits, category enum) + write-to-disk + rate-limit-fires-at-cap; frontend form rendering + submit success/error paths + auto-capture (worldId, viewport, bundleHash). **Deploy window:** queued alongside the font-size feature for Monday 2026-06-08, 05:00–08:00 PST. New env knob requires backend restart (~30 sec) — same restart as the font-size deploy, so single combined patch.
      _Discovered + resolved: 2026-06-07 | Context: Russell asked for an in-product feedback form during the alpha-feedback-tracking discussion. Decisions confirmed 2026-06-07 (no per-world token; gitignored repo-root storage; defer screenshots). Shipped same-day._

- [ ] **Inject bundle hash into the SPA via `VITE_BUNDLE_HASH` at build time.** Currently `apps/sentinel-ui/src/pages/Feedback.jsx` reads `import.meta.env.VITE_BUNDLE_HASH` for the on-disk `bundleHash` field in feedback submissions, defaulting to `'dev'` when unset. Today the env isn't injected, so every submission carries `bundleHash: "dev"` — losing the "which bundle did the tester have loaded?" provenance that's useful for triage. **Fix:** `vite.config.js` reads the asset chunk filename at build time (or a `git rev-parse --short HEAD` fallback) and emits `define: { 'import.meta.env.VITE_BUNDLE_HASH': JSON.stringify(hash) }`. Two-line config change + verify the build emits a non-`'dev'` value. Low priority — feedback works without it; just nicer-to-have triage signal.
      _Discovered: 2026-06-07 | Context: Russell's first form submission landed with `bundleHash: "dev"` — confirmed the fallback works but flagged the missing build-time injection._


### Red-team findings — alpha pass 2026-06-07

Construct-and-run red-team pass (10 surfaces, 16 raw findings, 16 verifier-reproduced, 8 grounded-as-real-bugs). **Closed alpha not blocked** — no containment breaks against the production threat model. Strong defenses confirmed holding under attack: MCP network isolation, `/api/world/{id}` token-before-lookup, path-traversal-via-id, per-world cross-process locks, XFF-spoof rejection (PR #92), namespace-via-query-param gate (red-team #7). Triage decisions recorded inline below; one schema-gate slice (#1) + one chore for dead-code removal (#3) are the actionable items this week.

- [ ] **(red-team #1, 2026-06-07) Schema-gate tightening — `untrusted_llm_path` failures.** Bundles four related schema-gate breaks all reachable via DM-emitted `<world_update>` → fact-extractor → fs-manager. Schema-valid is not operator-safe today. Decided 2026-06-07: one combined PR (`fix/schema-gate-tighten`), both fact-extractor pre-emit AND fs-manager write-boundary enforcement (defense in depth — fact-extractor for the fast-fail / DM-feedback UX, fs-manager for the universal catch-all that direct-MCP/migration scripts also hit).
      **The four breaks (all confirmed-reproduced + source-grounded):**
      1. **High — Schema-valid string/array `data` on a `.json` target bricks the file (per-world DoS).** `schemas/apply_world_update.schema.json:37-40` declares `data: ["object","string","array"]` with no `oneOf`/`if-then` gating the type by `target_file` extension. At `mcp-servers/fs-manager/server.py:433` (create) and `:451` (update), `execute_update` writes `str(data)` verbatim when `data` is not dict/list — INCLUDING to `.json` paths. The next `update` to that file's `json.loads` at line 446 raises `JSONDecodeError` (not caught by the `try/except OSError` at line 581), surfacing as a bare FastAPI 500. `check_protected_fields` (303-306) silently `continue`s non-dict items, so a string `data` bypasses `PROTECTED_FIELDS` enforcement too. Fact-extractor self-validates against the same permissive schema.
      2. **Medium — `append` op corrupts `.json` state files.** Schema permits BOTH `.json` and `.md` targets and admits `append` in the operation enum. The free-text descriptions say append is Markdown-only but it's not encoded as a conditional. `execute_update`'s `append` branch (lines 456-467) only validates `isinstance(data, str)` then `open(abs_path, "a")` — no `.endswith(".md")` guard. Model-emitted `operation=append + target_file=data/state/.../*.json + data="garbage"` survives the schema gate and corrupts the file (subsequent `json.loads` raises).
      3. **Medium — Control bytes / RTL-override / zero-width chars persist verbatim into session logs + community lore Markdown.** `mcp-servers/fs-manager/server.py:580` writes `payload['log_entry']` and `:466` writes `append`-op string `data` with no character constraint. Schema bounds `log_entry` length only — no `pattern`/`not` excludes C0 controls, ESC (`\x1b`), RTL overrides (U+202A–U+202E, U+2066–U+2069), or zero-widths (U+200B–U+200D, U+FEFF). `fact_extractor._build_log_entry` (319-332) only `.strip()` + truncates. Embedded control bytes survive into the operator-facing session log + the training corpus + the file-observer chatlog detector input.
      4. **Low — Protected-field check is case-sensitive — case-variant keys (`Unique_Id`, `WORLD_SEED`, `Namespace`) write through unchecked.** `mcp-servers/fs-manager/server.py:149-156` `PROTECTED_FIELDS` is a lowercase exact-case set, and `check_protected_fields` (line 307) does exact-string membership. Schema doesn't constrain `data` keys (`additionalProperties` unset), so case-variant keys pass everything. Severity is genuinely low (no code-reader uses case-insensitive lookups on these field names today) — forward-looking + on-disk noise injection.
      **Combined fix shape (one PR):**
      - **Schema:** add `allOf`/`if-then` to `apply_world_update.schema.json` so (a) `operation==append` implies `target_file` matches the lore regex AND `data` is `string`; (b) `data` is `object|array` when `target_file` ends `.json`; (c) `data: string` on session log adds a `not` pattern rejecting C0 controls (except `\t`/`\n`), `\x1b`, U+202A–U+202E, U+2066–U+2069, U+200B–U+200D, U+FEFF.
      - **fact-extractor (`engine/agents/fact_extractor.py`):** mirror the schema constraints — strip control bytes from log_entry, reject mismatched data types at extract time, feed back to DM as a schema-failure-as-control-flow (matches the existing pattern).
      - **fs-manager (`mcp-servers/fs-manager/server.py`):** belt-and-suspenders enforcement of the same constraints (`execute_update`'s `append` branch raises 422 unless `target_file.endswith(".md")`; `.json` target requires `isinstance(data, (dict, list))`; control-byte scrub at write boundary). Shared util `mcp-servers/_scrub_control_bytes.py` (or similar) — one regex, two enforcement points.
      - **case-fold protected-field check:** `lowered = {k.lower(): k for k in item}; violations = [lowered[f] for f in PROTECTED_FIELDS if f in lowered]` — report original-cased key in the 403 detail.
      - **Wrap `json.loads` at fs-manager:446** in `try/except (JSONDecodeError, ValueError)` so a pre-existing corrupted file degrades to structured `{code: CORRUPTED_STATE}` 500 rather than a bare 500.
      - **Tests:** regression for each of the 4 breaks — append-against-json returns 422, string-data-against-json returns 422, control-byte payload gets scrubbed or rejected, `Unique_Id` case-variant returns 403.
      **Reachability:** `untrusted_llm_path` — fs-manager binds 127.0.0.1 (line 626) + Caddy invariant-tested to never proxy :8010, so direct network reach is loopback-only, BUT the realistic vector is untrusted LLM output through the engine dispatch (the "loopback-only sink reachable via engine→fs-manager" failure mode the CLAUDE.md hunt list calls out).
      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07. Decision summary: one PR, fact-extractor + fs-manager both layers._

- [ ] **(red-team #2, 2026-06-07) Endpoint auth (per-world HMAC) on git-sync's destructive `teardown_world` — BEFORE PUBLIC SIGNUP.** `mcp-servers/git-sync/server.py:297-339` (`teardown_world`) accepts a bare `{world_id}` body, validates UUID + traversal, acquires the per-world lock, then unconditionally `shutil.rmtree`s the world repo with zero caller authentication, no session-token binding, no soft-delete. The comment at lines 551-555 acknowledges "the MCP write layer ... has no endpoint auth, so its safety is network topology," and ADR 0003 §3.4 names the gap explicitly. Reachability is loopback-only today (defended by CI-gated `tests/test_mcp_bind_invariant.py` + `tests/test_caddy_invariant.py`); BUT the gap collapses if anyone misconfigures `SENTINEL_ALLOW_PUBLIC_BIND=1`, manually edits the deployed (not committed) Caddyfile to proxy `:8012`, or a container shares the network namespace.

      **Decision 2026-06-07:** add **per-world HMAC** (NOT a separate shared secret). Extend the existing `SENTINEL_SESSION_TOKEN_SECRET` machinery: git-sync calls `world_token.verify(token, world_id, secret=...)` on destructive ops, using the same HMAC the backend already mints. Symmetric with `backend/auth/`, no new secret to manage, composes naturally with Monday's per-tester reauth work (per-user binding → "user X destroyed world Y" auditability from the same HMAC chain).

      **Fix shape:**
      - `mcp-servers/git-sync/server.py`: import (or vendor) `world_token.verify`. `teardown_world` reads `X-Sentinel-World-Token` header, calls `verify(token, world_id, secret=os.environ['SENTINEL_SESSION_TOKEN_SECRET'])` — 401 if missing, 403 if invalid.
      - `engine/dispatch/git_sync.py`: thread the per-world token through to MCP calls. The backend already mints one at session-create; engine just needs to carry it via the dispatch config.
      - **Tests:** regression for "unauthenticated curl to teardown_world returns 401"; "wrong-world token returns 403"; "valid token succeeds + repo gone".
      - **Belt-and-braces (optional v2):** soft-delete (`<world_id>.deleted-<ts>/` + separate purge job) so a single curl can't be irreversible.

      **Tag: BEFORE PUBLIC SIGNUP.** Not a closed-alpha blocker (the CI-gated network-isolation invariants are stronger than "one misconfiguration"; realistic attackers today are testers behind basic_auth at gate, NEVER on origin-core's tailnet directly per [[project_tailnet_claude_owns_public_edge]]). Promote to blocker when the alpha graduates from invite-only-with-shared-creds to broader signup. Supersedes the existing optional defense-in-depth note at `docs/BACKLOG.md:232`.

      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07. Reaffirms ADR 0003 §3.4's deferred-by-design note._

- [ ] **(red-team #3, 2026-06-07) Remove `rollback_to` from git-sync — dead code from a superseded design.** `mcp-servers/git-sync/server.py:521-548` (`rollback_to`) was added in the project skeleton commit (`413e5be`, 2026-03-24) and references "the Orchestrator" in its docstring — a long-defunct agent architecture; the current design is DM → Fact-Extractor → fs-manager + git-sync, no orchestrator. **Zero callers in `engine/`, `backend/`, or the SPA** (verified via grep) — only `tests/git_sync/test_server.py:330` references it. The endpoint has the same auth gap as `teardown_world` (red-team #2) but no operational utility to justify either keeping it OR adding auth.

      **Fix:** delete the route + its test in a small `chore/remove-rollback-to` PR.

      **NOT adapted into the new feature** (per Russell's call 2026-06-07): an operator-side "restore world to prior turn" tool is a useful future feature, but it should be **specced from scratch as a real product feature**, not retrofit onto stale dead code. See the new "Operator: restore world to prior turn / commit" BACKLOG entry below for the spec slot.

      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07 — endpoint surfaced as both attack surface and dead-code candidate; decision to remove + re-spec deliberately._

- [ ] **(red-team #4, 2026-06-07) Sanitize git-sync error bodies — don't pass `GitCommandError.__str__()` through to HTTP responses.** `mcp-servers/git-sync/server.py:291` (in `init_world`), `:395` (in `commit_snapshot`), `:486` (also in `commit_snapshot`), `:517` (in `list_snapshots`), `:545` (in `rollback_to`) all stringify the raw exception (`detail=str(e)`) into the `HTTPException` body. GitPython's `GitCommandError.__str__()` emits `"Cmd('git') failed... cmdline: <full args>\n stderr: <verbatim git stderr>"` — attacker-controlled inputs come back along with git's stderr (information disclosure / probe channel). Confirmed reproducible at the three sites the red-team probed; gemini code-review added `:291` + `:517` from a static grep (verified — all five sites have the identical `detail=str(e)` pattern). Not a containment break — `:8012` is loopback/tailnet-only per ADR 0003 + `test_caddy_invariant.py`, and `rollback_to` has no engine/backend caller. **Fix:** in all five `except` blocks, keep `logger.error(str(e))` (server-side detail) but return a sanitized body — `detail={"code": "GIT_ERROR", "detail": "git operation failed; see server logs"}` plus an opaque correlation id; for `GitCommandError` specifically extract only `e.status` and a generic message. The two repo-not-found branches in `commit_snapshot` (471-482) already model the curated-detail pattern. Note: red-team #3 (remove `rollback_to`) drops `:545` along with the whole function, so the schema-gate PR ends up touching only the four remaining sites. **Bundles cleanly with red-team #2's PR** (same file).
      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07._

- [ ] **(red-team #5, 2026-06-07) Operator: restore world to prior turn / commit — feature spec, NOT adapted dead code.** Decided 2026-06-07 alongside the rollback_to removal (red-team #3). A useful operator capability — when a DM hallucination ruins a session or a tester reports a regression we want to undo — is the ability to step a world's git repo back to a prior turn (commit). The dead `rollback_to` MCP endpoint was structurally close but auth-deficient + reachable from the wrong layer; this entry is for **the real feature, specced purposefully from scratch**.

      **Sketch (to be refined when triggered):**
      - **Auth:** operator-only via the admin dashboard (loopback/tailnet-bound at `/api/admin/world/<id>/restore`, behind the same Caddy `handle /api/admin* { respond 404 }` invariant that hides operator endpoints from the public edge). NOT player-callable.
      - **UI:** small "Restore" affordance on the operator status dashboard (`/_status`) showing the world's recent per-turn commits with one-click restore.
      - **Backend route:** `POST /api/admin/world/<id>/restore` accepting `{commit_hash | turn_number}` — backend resolves to a commit, calls a new git-sync endpoint (NOT the dead `rollback_to`, a fresh one with proper auth + audit logging).
      - **git-sync endpoint:** `POST /tools/restore_world` — same auth shape as `teardown_world` post-#2 (per-world HMAC), atomic write via fs-manager lock, audit-log entry in `<WORLDS_ROOT>/<world_id>/.audit.log` capturing operator + commit + timestamp.
      - **Player visibility:** the world's SSE stream surfaces a system event ("World restored to turn N by operator") so the player isn't confused by missing turns; the SystemLog tab gets a styled entry.
      - **Safety:** soft-delete pattern — restoring creates a new commit (a "revert" merge) rather than `git reset --hard`, so the discarded path stays in reflog for recovery if the restore was itself a mistake.

      **Trigger:** the first real operator need — a tester reports a DM hallucination that wrecked their session and Russell wants to undo it. Until then, the `git-sync` repo IS the audit trail; manual `git checkout` works for emergency operator recovery.

      _Discovered: 2026-06-07 | Context: emerged from the rollback_to-removal discussion — Russell's framing: "A useful feature we should add to the backlog and spec purposefully and not adapt dead code."_

- [ ] **(red-team #6, 2026-06-07, informational) Move `enforce_world_token` above the session lookup on POST /api/stream — sibling-path inconsistency with /api/world.** `backend/routes/stream.py:174-198` calls `find_session_data_dir` + `read_session` and raises HTTP 400 "Session not found or inactive" at line 183 *before* `enforce_world_token` runs at line 198, making the route an unauthenticated existence oracle for `session_id`s. The sibling world-scoped route `backend/routes/world.py:113-145` does the opposite + documents the invariant at line 131 ("Checked before the lookup so existence isn't leaked to an unauthorized caller"). Practical attack value near-zero (session IDs are unguessable v4 UUIDs, no enumeration endpoint exists), BUT the two world-scoped routes apply opposite policies under the same threat model — the kind of sibling-path inconsistency the CLAUDE.md hunt list calls out. **Fix:** move the `enforce_world_token(request, settings, body.world_id or "")` call above the lookup; to preserve "stream token for world A can't drive a session in world B," either (a) require `body.world_id` and enforce token against it first, then verify `session.world_id == body.world_id` after lookup (same generic 4xx on mismatch as not-found), or (b) return uniform 401/403 for both bad-token and not-found when enforcement is on. **Promote the invariant to a test** so the sibling-path regression doesn't recur — "world-scoped routes must enforce token before lookup." **Bundles cleanly with the per-tester reauth Monday work** (same `enforce_world_token` call site is affected).
      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07._

- [ ] **(red-team #7, 2026-06-07) Community-pack subtree writes lack registry — `untrusted_llm_path` reachable, theoretical today.** `mcp-servers/fs-manager/server.py` `validate_path` (318-327) accepts any `[a-zA-Z0-9_-]+` as the `<pack>` segment under `data/state/community/<pack>/` and `data/lore/community/<pack>/`. `validate_namespace` (330-356) only gates `CORE_GATED_PATH_PATTERN`; community paths are out of scope. No `community.json` / `pack_id` enforcement exists anywhere in the codebase (grep returns zero hits). ARCHITECTURE.md §2's invariant ("Community writes are restricted to data/state/community/<pack-name>/") and §3's documented manifest gateway are unimplemented; BACKLOG (lines 290-297, 316, 332) already concedes the framework "exists on paper" only. An LLM-emitted `<world_update>` with `target_file: data/state/community/victimpack/secret.json` flows engine→fs-manager and is accepted. Impact today is theoretical (zero community packs on disk; single-tenant local play). **Fix:** finish the `community.json` gateway envisioned in ARCHITECTURE.md §3 — load pack manifests on startup, register declared paths, reject writes whose `<pack>` segment isn't in the registered set. Add a `pack_id` scope to the dispatch query (analogous to `namespace=core`, set by trusted backend, NOT LLM-asserted). Stopgap: `SENTINEL_COMMUNITY_PACKS_ALLOWLIST` env var. Tracks under the existing community-gateway section. **Not urgent for closed alpha** — defer until first community pack ships.
      _Discovered: 2026-06-07 | Context: red team pass 2026-06-07._

- [ ] **Tester self-signup page — eliminate operator-in-the-middle for credential provisioning. TARGETED FOR TUESDAY 2026-06-09 PATCH WINDOW.** Russell 2026-06-08: "Players will choose [usernames], no me in the middle hopefully... I prefer the signup page where all I have to do is green light a list rather than human engineering." With Monday's per-tester reauth, **recovery** is self-service (SPA auto-calls `/reauth` on 401, no human relay needed). But **initial provisioning** without this feature still requires the operator-as-relay: invitee picks username + password, sends to operator, operator relays to tailnet Claude, tailnet adds the Caddyfile entry. One-time-per-invitee but humans-in-loop. This entry replaces that with: operator green-lights a list of pending signups via the admin dashboard, materialization to Caddy is automated.

      **Structural problem:** Caddy basic_auth credentials live in the deployed Caddyfile's `basic_auth { ... }` block. No API to add a credential — requires editing the file + reloading Caddy. Self-signup needs an intermediary that holds pending invites and either (a) writes to Caddy on tailnet Claude's behalf or (b) generates the bcrypt hash + opens a PR/file-change for tailnet to apply.

      **Sketch (refine when triggered):**
      - **Invite generation:** the operator creates an invite via the admin dashboard (`/api/admin/invite`) returning a single-use signup URL like `https://<DOMAIN>/alpha/signup?token=<one-time>`. Token signed (HMAC over invite_id + expiry); 24-hr TTL. **Stateful single-use enforcement required (gemini medium on PR #122 re-review):** HMAC alone gives signature integrity + expiry, but it CANNOT prevent replay/reuse within the TTL window — a stateless token has no notion of "spent." Combine the HMAC with an on-disk consumed-invite ledger: `<WORLDS_ROOT>/.invites/<invite_id>.consumed` (or a flat append-only `<WORLDS_ROOT>/.invites/log.jsonl` keyed by invite_id). On `/api/signup`, take a per-invite filelock, check ledger, mark consumed atomically (open-O_EXCL on the `.consumed` marker), then proceed. Without this dual control (HMAC + ledger), the same invite link reused N times within 24-hr TTL creates N accounts.
      - **Signup page:** `/alpha/signup` — Caddyfile exception OR a `signup.<DOMAIN>` subdomain to bypass the basic_auth gate for this single route. Page asks for username + password + (optional) display name. POSTs to `/api/signup` carrying the invite token.
      - **Backend `POST /api/signup`:** verifies the HMAC + checks expiry, validates username unique + valid format, bcrypts the password, writes to a pending-invites queue (or emits a Caddyfile fragment), **atomically marks the invite_id consumed on the ledger** (open-O_EXCL on the marker file under the per-invite filelock), returns success. Race-safe: two concurrent submissions of the same token serialize on the lock + only one succeeds at the marker write; the second observes the marker exists and 410-Gones (invite already used).
      - **Operator approval step:** admin dashboard shows the pending-signup queue with one-click "green light" approval. The operator never sees the bcrypt hash directly — they approve by `(username, display-name, IP, submitted-at)` rather than by credential material.
      - **Tailnet integration:** tailnet Claude (or the operator) consumes the APPROVED queue periodically (or via webhook) → materializes credential into deployed Caddyfile + reloads. Alternate: sentinel publishes the credential block as an env file that Caddy's `EnvironmentFile=` reads on reload, no manual edit needed.
      - **UX edges:** invite reuse rejection, username-already-taken, password strength, cancellation flow.
      - **Audit:** every signup logs `invite_id`, `chosen_username`, `display_name`, `timestamp`, `client_ip`, and a non-sensitive `credential_id` (a short opaque pointer to the credential record). **DO NOT log the bcrypt hash** (codex P2 on PR #122): hashes are credential material; storing them in audit logs broadens credential exposure to anyone with log access AND creates an offline-cracking target if logs ever leak. The Caddyfile/env credential materialization path is the only place the hash should reach; the audit trail records `credential_id` so we can correlate an audit entry to its credential without making the audit row itself a credential dump.

      **Trigger:** TARGETED for Tuesday 2026-06-09 05:00–08:00 PST patch window. Pre-stage the implementation Sunday evening / Monday so Tuesday morning is review + merge + deploy, not coding from scratch. Coordinate with tailnet Claude on the deployed-Caddyfile-writeback story (env-file vs explicit reload-with-fragment) in parallel.

      _Discovered: 2026-06-08 | Context: surfaced during the Monday-patch-window prep — per-tester reauth solves recovery but leaves initial provisioning manual. Russell explicitly preferred "green light a list" over human-engineering relay. Targeted for the Tuesday window per the daily-cadence pattern._

- [ ] **Lint: `setLocation` declared but unused in `apps/sentinel-ui/src/pages/Feedback.jsx:47`.** `const [, setLocation] = useLocation();` — neither `setLocation` nor the `useLocation` import is exercised. Pre-existing dead code from PR #116 (the feedback form ship); slipped because no CI lint gate runs JS lint. Two-line cleanup: delete the destructure line + drop `useLocation` from the wouter import. **Trigger:** any time someone touches Feedback.jsx, or as a backlog-sweep cleanup. Low priority.
      _Discovered: 2026-06-08 | Context: surfaced while running `pnpm lint` during the tension-drives-encounters PR readiness check._

- [ ] **Scanner artefacts land in `data/state/` (gitignore gap).** File-observer v1.12+ drops `manifest_v<ver>_<ts>.json` + `report_v<ver>_<ts>.md` pairs into whatever dir it scans. Two of the scanned surfaces — `chatlogs/` and `datasets/chatlogs/` — are already gitignored, but `data/state/` is canonical world state under git, so a scanner pass dirties the working tree until the artefacts are removed or ignored. Add `data/state/manifest_v*` + `data/state/report_v*` (or a `manifest_v*` / `report_v*` glob across the canonical-state surfaces) to `.gitignore`. Cross-link: `[[project_chatlog_home]]` for the broader scanner ↔ sentinel substrate/interpreter split.
      _Discovered: 2026-06-08 | Context: noticed during the Sunday-evening scan drop — three pairs landed; chatlogs/ + datasets/chatlogs/ already ignored, data/state/ is not._

- [ ] **Soft-contract flag: scanner's chatlog speaker-label detection returns 0-or-1 speakers for our jsonl format.** 2026-06-07 scanner pass on `/srv/projects/project-sentinel/chatlogs/` (9 Claude Code session jsonls, 42 turns total) reports `distinct_speakers: ['assistant']` — the user/human side isn't being matched. Same pattern on `datasets/chatlogs/` (1 file, 4 turns, 0 speakers). The soft contract is `CHATLOG_SPEAKER_LABEL_RE` (schema 1.3), which `backend/datasets.py::build_chatlog` mirrors — per memory `[[project_chatlog_home]]`, neither side changes it without routing through Russell first. Likely either (a) the Claude Code jsonl format diverged from what schema 1.3 expects, or (b) a scanner regression in the speaker-detection regex. **Action:** flag back to file-observer side (cross-pollination, not coordinated work). For sentinel: confirm whether `build_chatlog` is downstream-affected (probably not — it processes via its own normalized pipeline, not via the scanner's regex). **Trigger:** ad-hoc, low urgency — file-observer Claude's lane to investigate.
      _Discovered: 2026-06-08 | Context: surfaced during triage of the 2026-06-07 scanner drop in `data/state/` / `datasets/chatlogs/` / `chatlogs/` — only signal worth flagging out of three reports._
