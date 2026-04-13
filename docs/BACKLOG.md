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

- [ ] **Build the Inference Node from scratch.** `world-engine/` is legacy Replit scaffolding (just three prompt YAMLs, no orchestrator, no entry point). The real Inference Node — DM → Fact-Extractor → schema-validated `<world_update>` → MCP dispatch → Lorekeeper re-inject — needs a greenfield design: where it lives, how it's invoked (Django management command vs. inline from the SSE view vs. background worker), and whether any of the existing agent YAMLs are reused. No code until that design exists.
      _Discovered: 2026-03-28, updated 2026-04-13 | Context: originally filed as "verify orchestrator/main.py exists"; user confirmed world-engine/ is not the target — Inference Node will be built fresh. README "Initialize the Inference Loop" section has been marked "not yet implemented" pending this design._

---

## Architecture & Structure

- [ ] **Auth strategy decision (future):** three clear paths — (1) simple API key middleware for single-player public deployment, (2) DRF TokenAuthentication + Django User model for multi-user, (3) outsourced JWT (Auth0/Clerk/Supabase) if password management is unwanted. SSE streaming endpoint has no conflict with any of these — auth middleware runs before the stream opens. Decision not needed for 1.0.
      _Discovered: 2026-03-27 | Context: discussed during Django backend planning; single-player for 1.0 means no auth required now_

- [ ] **DRF adoption decision (future):** not needed for 1.0. Worthwhile if: (a) multi-user auth is added, (b) entity CRUD grows beyond list/read, (c) `_serialize_*` helpers in views.py become a maintenance burden. SSE endpoint will always be raw Django regardless of DRF adoption.
      _Discovered: 2026-03-27 | Context: discussed during Django backend planning_

---

## Developer Experience

- [ ] Add unit and integration tests for `apps/sentinel-ui/` — Zustand stores, API client, and key components
      _Discovered: 2026-03-26 | Context: flagged in PR #5 review; no tests exist for any of the 8 frontend phases; recommend vitest + @testing-library/react_

- [ ] Add machine-readable requirements manifest (Brewfile or .tool-versions) for `just`, `chezmoi`, and other non-npm tools
      _Discovered: 2026-03-25 | Context: docs list prerequisites but no single install command exists for a new contributor_
