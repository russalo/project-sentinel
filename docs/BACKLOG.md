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

## High Priority — Do Soon

- [ ] **Decide source-of-truth: Postgres vs. `data/state/*.json`.** Blocks Fact-Extractor implementation. Current MVP (`backend/api/dm_ai.py`) writes straight to Postgres via Django ORM, bypassing the MCP Bridge entirely; `ARCHITECTURE.md` says the hybrid filesystem under `data/` is canonical and Postgres is a projection. Three viable answers: (1) keep Postgres canonical, route writes through fs-manager as secondary export; (2) make `data/` canonical, have Django read from it; (3) split — Postgres for hot session/turn state, `data/` for canonical lore + entity snapshots at commit boundaries. The output shape of `engine/agents/fact_extractor.py` depends on which one.
      _Discovered: 2026-04-13 | Context: surfaced while planning the engine/ scaffold PR; documented as the primary blocker on Fact-Extractor work_

- [ ] **Implement `engine/agents/fact_extractor.py`.** Bridges the two `<world_update>` shapes — the ORM-flavored hint the DM prompt emits vs. the filesystem-operations contract in `schemas/apply_world_update.schema.json`. Pure function: raw DM response + session_id → schema-valid payload. Testable in isolation (no Django, no network). Blocked on the source-of-truth decision above.
      _Discovered: 2026-04-13 | Context: scaffolded as a NotImplementedError stub in commit 6d2a9f9; next concrete implementation step for the engine package_

- [ ] **Wire `engine/` into `backend/api/views.py` and retire `backend/api/dm_ai.py`.** After the Fact-Extractor lands and the DM agent is implemented, the Django SSE view should call `engine.agents.dm.stream_turn()` instead of the current inline OpenAI call, and the Fact-Extractor output should be dispatched to fs-manager. At that point `backend/api/dm_ai.py` is dead code and gets deleted.
      _Discovered: 2026-04-13 | Context: sequencing step after the Fact-Extractor implementation — see engine/README.md for the boundary contract callers must honor_

- [ ] **Delete `world-engine/` entirely once `engine/` is wired in.** The three prompt YAMLs (`dm.yaml`, `fact-extractor.yaml`, `lorekeeper.yaml`) may be useful reference when writing `engine/prompts/*.py`, so keep them until the engine agents are implemented, then remove the directory in a dedicated cleanup commit. Also remove `world-engine` from `scripts/check-structure.sh` at the same time.
      _Discovered: 2026-04-13 | Context: world-engine/ was retained during the engine/ scaffold PR to avoid deleting reference material prematurely; finish the cleanup once it has served its purpose_

---

## Architecture & Structure

- [ ] **Auth strategy decision (future):** three clear paths — (1) simple API key middleware for single-player public deployment, (2) DRF TokenAuthentication + Django User model for multi-user, (3) outsourced JWT (Auth0/Clerk/Supabase) if password management is unwanted. SSE streaming endpoint has no conflict with any of these — auth middleware runs before the stream opens. Decision not needed for 1.0.
      _Discovered: 2026-03-27 | Context: discussed during Django backend planning; single-player for 1.0 means no auth required now_

- [ ] **DRF adoption decision (future):** not needed for 1.0. Worthwhile if: (a) multi-user auth is added, (b) entity CRUD grows beyond list/read, (c) `_serialize_*` helpers in views.py become a maintenance burden. SSE endpoint will always be raw Django regardless of DRF adoption.
      _Discovered: 2026-03-27 | Context: discussed during Django backend planning_

---

## Documentation Drift

- [ ] **`docs/WORKSPACE.md` is stale from before the Django backend and the engine package.** Lists "API framework: Express 5" as if Django doesn't exist; the Stack table has no row for `backend/`; the directory tree has no `backend/` or `engine/`; the AI Architecture section only describes `artifacts/api-server/src/lib/dm-ai.ts`. Needs a full refresh, or a clear marker saying it only describes the TypeScript/Express dev-reference half of the workspace.
      _Discovered: 2026-04-13 | Context: surveyed during the engine/ scaffold PR doc audit; pre-existing drift, not touched in that PR to keep scope focused_

- [ ] **`CHANGELOG.md` `[Unreleased]` section is empty of ~6 months of work.** No entries for PR #7 (Django backend + SSE), PR #5 (frontend clean build), Replit migration, `just`/chezmoi tooling, Lane A housekeeping, or the engine scaffold. Either catch it up in one pass from git history and resume maintenance, or add a note at the top that the changelog is currently unmaintained so contributors aren't misled.
      _Discovered: 2026-04-13 | Context: surveyed during the engine/ scaffold PR doc audit; pre-existing drift, not touched in that PR_

---

## Developer Experience

- [ ] Add unit and integration tests for `apps/sentinel-ui/` — Zustand stores, API client, and key components
      _Discovered: 2026-03-26 | Context: flagged in PR #5 review; no tests exist for any of the 8 frontend phases; recommend vitest + @testing-library/react_

- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
