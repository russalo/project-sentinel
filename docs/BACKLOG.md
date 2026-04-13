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

- [ ] **Implement `engine/dispatch/` HTTP module for MCP Bridge calls.** Thin client wrapping `fs-manager:8010`, `git-sync:8012`, and eventually `db-vector:8011` over HTTP. Takes a `Config` (already defined in `engine/types.py`) with server URLs. Pure Python, testable in isolation against a mock FastAPI server. This is the channel through which the Fact-Extractor's output reaches the filesystem — without it the engine can't actually write anything.
      _Discovered: 2026-04-13 | Context: called out in ADR 0001 § Implementation implications; blocks the Fact-Extractor PR_

- [ ] **Implement `engine/agents/fact_extractor.py`.** Output shape is now pinned by ADR 0001: produces `schemas/apply_world_update.schema.json`-valid payloads with `fs-manager` as the single consumer. Pure function — raw DM response + session context → validated payload. Full unit test suite (no Django, no network, no filesystem; mock the `engine/dispatch/` layer in tests). The Fact-Extractor is the bridge between the DM-prompt-flavored `<world_update>` hint the LLM emits and the filesystem-operations contract fs-manager enforces.
      _Discovered: 2026-04-13 | Context: scaffolded as a NotImplementedError stub in PR #9; unblocked by ADR 0001; output shape was the previous blocker_

- [ ] **Implement `engine/agents/dm.py`** (`run_turn` + `stream_turn`). Wraps the OpenAI chat completion call. `stream_turn` is a plain generator yielding token strings — the caller (FastAPI SSE endpoint, future FastAPI adapter, test fixture) wraps that generator in whatever transport they need. Ports `DM_SYSTEM_PROMPT` consumption logic out of `backend/api/dm_ai.py` (the prompt itself is already in `engine/prompts/dm.py`). No Django, no ORM, no side effects.
      _Discovered: 2026-04-13 | Context: scaffolded as NotImplementedError stubs in PR #9; paired with the Fact-Extractor as the "engine actually runs a turn end-to-end" milestone_

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

- [ ] **Drop Postgres entirely from the Docker stack.** ADR 0001 Phase 2. Remove `sentinel-postgres` from `infrastructure/docker-compose.yml`, delete `infrastructure/migrations/*.sql`, remove psycopg2 and database URL wiring from any remaining code, update `just` recipes and health checks. Only do this once Phase 1 has proven that the Postgres cache layer is never load-bearing — in practice, that probably means Phase 1 ships reading directly from `data/` and Postgres is quietly never used.
      _Discovered: 2026-04-13 | Context: ADR 0001 Phase 2; explicitly deferred until Phase 1 is stable_

- [ ] **Rewrite `README.md` and `ARCHITECTURE.md` Core Loop narratives to match running code.** Once Phase 1 lands and `data/` is actually canonical in the code, the documents can be rewritten from "describes the target architecture" to "describes the running system." Until then they carry forward-pointing callouts to ADR 0001. This is the good kind of documentation debt: deferred intentionally because writing it now would be writing aspiration, and writing it after the code lands will be writing reality.
      _Discovered: 2026-04-13 | Context: ADR 0001 implementation implications; explicitly not done in the ADR PR_

- [ ] **Revisit the `db-vector` MCP server's role.** Currently designed as "route structured queries to Postgres, semantic queries to ChromaDB." Under ADR 0001 Phase 2, Postgres goes away, so `db-vector` becomes either a ChromaDB-only wrapper or a unified read layer over `data/` + ChromaDB. Decide what it is during Phase 2.
      _Discovered: 2026-04-13 | Context: ADR 0001 Consequences § Neutral — flagged as requiring a design decision during Phase 2_

- [ ] **Lorekeeper agent + ChromaDB indexing.** Once the core loop is running end-to-end under the new backend, add the RAG step. Index `data/lore/**/*.md` into ChromaDB on startup and on filesystem change (either a file watcher or a restart-only indexer). The Lorekeeper agent queries ChromaDB for context and injects results into the next DM turn. `engine/agents/lorekeeper.py` doesn't exist yet — scaffold + implementation are both part of this item.
      _Discovered: 2026-04-13 | Context: ADR 0001 mentions this as "later" — not a Phase 1 concern, but the natural next step after the core engine loop is running_

- [ ] **Background simulation / world progression.** The "world keeps evolving while you sleep" piece from the README tagline. Cron-driven agent runs that mutate `data/` via the same engine → fs-manager path as player turns. Needs a locking story so simulation writes don't collide with player turns (file-level lock via fs-manager, or sequencing via a queue). Not Phase 1.
      _Discovered: 2026-04-13 | Context: referenced in ARCHITECTURE.md §7 (orchestrator/simulation); currently not scaffolded; Phase 2 or later_

---

## Architecture & Structure

- [ ] **Auth strategy decision (future):** three clear paths — (1) simple API key middleware for single-player public deployment, (2) DRF TokenAuthentication + Django User model for multi-user, (3) outsourced JWT (Auth0/Clerk/Supabase) if password management is unwanted. SSE streaming endpoint has no conflict with any of these — auth middleware runs before the stream opens. Decision not needed for 1.0. **Note:** per ADR 0001, option (2) is no longer on the table — Django is retiring. The multi-user path would likely be FastAPI middleware + a JWT library or an outsourced identity provider.
      _Discovered: 2026-03-27 | Updated: 2026-04-13 | Context: originally discussed during Django backend planning; updated after ADR 0001 retired Django as an option_

- [ ] **DRF adoption decision (future):** ~~not needed for 1.0~~ **No longer applicable.** ADR 0001 retires Django, which makes Django REST Framework moot. Any equivalent question under FastAPI (e.g. "at what point do we switch from raw route handlers to Pydantic models everywhere?") would be a separate discussion.
      _Discovered: 2026-03-27 | Updated: 2026-04-13 | Context: superseded by ADR 0001_

---

## Documentation Drift

- [ ] **`docs/WORKSPACE.md` is stale from before the Django backend and the engine package.** Lists "API framework: Express 5" as if Django doesn't exist; the Stack table has no row for `backend/`; the directory tree has no `backend/` or `engine/`; the AI Architecture section only describes `artifacts/api-server/src/lib/dm-ai.ts`. **Note:** after ADR 0001 lands, this document will be even more wrong — it should be rewritten against the FastAPI backend + `data/` canonical model, not against the current Django code. Defer until Phase 1 ships, then write it once against reality.
      _Discovered: 2026-04-13 | Updated: 2026-04-13 | Context: originally filed during the engine/ scaffold PR doc audit; now additionally gated on ADR 0001 Phase 1_

- [ ] **`CHANGELOG.md` `[Unreleased]` section is empty of ~6 months of work.** No entries for PR #7 (Django backend + SSE), PR #5 (frontend clean build), Replit migration, `just`/chezmoi tooling, PR #9 (Lane A housekeeping + engine scaffold), or anything since. Either catch it up in one pass from git history and resume maintenance, or add a note at the top that the changelog is currently unmaintained so contributors aren't misled.
      _Discovered: 2026-04-13 | Context: surveyed during the engine/ scaffold PR doc audit; pre-existing drift, not touched in that PR_

---

## Engine Package

- [ ] **`engine/schema.py` schema-path coupling.** `_SCHEMA_PATH` is hard-coded to `Path(__file__).parent.parent / "schemas" / ...`, which only resolves correctly when `engine/` sits at the repo root alongside `schemas/`. The PR #9 boundary contract states `engine/` should be extractable into a standalone package; in that scenario this path breaks. Fix options: (a) bundle the schema as package data and load via `importlib.resources`, (b) copy `schemas/` into `engine/` as a sibling of `engine/schema.py`, or (c) have the caller inject the loaded schema or its path. Option (c) is the cleanest architecturally but changes `validate()`'s public API. Defer until extraction actually happens.
      _Discovered: 2026-04-13 | Context: flagged by Copilot on PR #9; documented in the module docstring of engine/schema.py and deferred to this item instead of reworked in the scaffold PR_

---

## Developer Experience

- [ ] Add unit and integration tests for `apps/sentinel-ui/` — Zustand stores, API client, and key components
      _Discovered: 2026-03-26 | Context: flagged in PR #5 review; no tests exist for any of the 8 frontend phases; recommend vitest + @testing-library/react_

- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
