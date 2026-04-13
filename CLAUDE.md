# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Agent Instructions — Project Sentinel

This file contains standing instructions for AI agents (Claude Code and others) working
in this repository. Read this before planning or implementing anything.

---

## Backlog Maintenance

The file `docs/BACKLOG.md` is the single source of truth for work that was discovered,
deferred, or left incomplete. You are required to keep it current.

**During a coding session, append to `docs/BACKLOG.md` when you:**
- Discover a bug, inconsistency, or technical debt that is out of scope for the current task
- Identify something that should be done soon but was not part of your planning
- Leave a task incomplete because it requires more information or a separate planning session
- Notice that documentation is out of sync with the current state of the code

**At the end of a session, remove from `docs/BACKLOG.md` when:**
- An item was fully resolved during the session
- An item is no longer relevant due to a direction change

**Format for new entries:**
```
- [ ] Short description of the item
      _Discovered: YYYY-MM-DD | Context: brief note on where/why this surfaced_
```

Add items under the most appropriate existing section. If no section fits, add one.
Never leave `docs/BACKLOG.md` in a state where completed work is still listed as pending.

---

## Explicit Approval Required Before Implementation

**You must not create, edit, or delete any file until the user has explicitly approved
a plan in the current session.**

This rule has no exceptions. "The plan seemed clear" is not an exception. "The user
approved something similar before" is not an exception. "The task is small" is not
an exception.

**Allowed without approval:**
- Reading files, exploring the codebase, running read-only commands
- Writing or updating the plan file at `/root/.claude/plans/`
- Asking clarifying questions

**Not allowed until the user says to proceed:**
- Creating new files
- Editing existing files
- Deleting files
- Running commands that modify state (git commits, installs, etc.)

If you have written a plan and are ready to implement, present it and stop. Wait for
the user to explicitly say to proceed — words like "go ahead", "do it", "looks good",
or equivalent. An acknowledgment that you answered a question correctly ("ok", "that
makes sense") is **not** approval to implement.

If you catch yourself about to write a file without approval, stop and ask.

---



You are expected to think critically, not just execute. Before implementing:

- If a directive is ambiguous, ask a clarifying question rather than assuming
- If you believe the approach has a meaningful tradeoff, name it explicitly
- If a requested tool, pattern, or dependency introduces lock-in or complexity that
  may not be worth the benefit, say so with your reasoning
- If something you were asked to do turns out to be more complex than expected,
  stop, surface the complexity, and propose that it go to the backlog rather than
  delivering a partial or risky implementation

Healthy critique is part of the job. Silent compliance that ships a wrong answer is not.

---

## Development Branch

All work goes to `claude/setup-cloud-environment-VGYBM` unless explicitly directed otherwise.
Never push to `main` directly.

---

## Directory Conventions

- `docs/` — project documentation and working reference files (BACKLOG.md lives here)
- `scripts/` — shell scripts for automation and dev lifecycle
- `mcp-servers/` — Python MCP server implementations
- `infrastructure/` — Docker Compose and environment configuration
- `tests/` — test suites (pytest for Python, pnpm test for TypeScript)
- `artifacts/` — deployable application packages (structure under review; see BACKLOG)
- `lib/` — shared libraries (structure under review; see BACKLOG)

---

## Things to Know About This Project

- This is a cross-OS project. Do not write scripts or configs that assume linux-only.
- Replit was the original development platform. We are migrating away from it.
  Do not introduce new `@replit/*` dependencies. See `docs/BACKLOG.md` for the
  full audit and removal plan.
- The frontend strategy for 1.0 is undecided. Do not build new frontend features
  without explicit direction.
- `just` is the command runner. Add new recipes to `justfile` rather than creating
  standalone scripts unless the logic is complex enough to warrant a separate file.

---

## Common Commands

`just` is the entry point for everything. `just` with no args lists all recipes.

**Setup**
- `just env` — regenerate `infrastructure/.env` from the chezmoi template (OS-aware: Docker socket path, Python binary)
- `just install` — one-stop installer: pnpm workspace + all Python deps (three MCP servers, Django backend, engine package, and pytest for tests). Fresh clone should be runnable after `just env && just install`.
- `just install-django` — standalone Django-only installer; used by `just install` and still available as a convenience alias when you only need to refresh backend deps.

**Run the stack**
- `just start` — full cloud stack: Docker (PostgreSQL + ChromaDB) → wait healthy → all three MCP servers in background
- `just health` — pass/fail table for every service; exits non-zero if anything is down
- `just reset` — wipe Docker volumes and restart from scratch
- `just up` / `just down` / `just down-volumes` / `just ps` / `just logs [service]` — raw Docker Compose passthroughs
- `just fs-manager` / `just db-vector` / `just git-sync` — run an individual MCP server in verbose dev mode on its port (8010 / 8011 / 8012)

**Dev servers**
- `just dev-backend` — FastAPI backend on `:8001` (`uvicorn backend.main:app --reload`)
- `just dev-frontend` — `apps/sentinel-ui` Vite dev server
- `just dev` — frontend + backend together
- `just install-backend` — reinstall backend Python deps alone (used internally by `just install`)

**Build & typecheck**
- `just build` — `pnpm build` across the workspace
- `just typecheck` — `pnpm typecheck` (no emit)

**Tests**
- `just test` — Python schema tests + all workspace JS tests (`pnpm -r --if-present run test`)
- `just test-schemas` — Python schema validation only (`pytest tests/`)
- Single Python test: `pytest tests/path/to/test_file.py::test_name`
- Single JS package: `pnpm --filter <pkg-name> test`

**Session lifecycle**
- `just start-session` — fetch, branch status, open backlog items, structure check
- `just end-session` — backlog + structure reminder before closing
- `just check-structure` — verify all documented paths exist

---

## Architecture at a Glance

> **Read this first:** the source-of-truth decision is recorded in **[ADR 0001](docs/adr/0001-data-canonical-source-of-truth.md)**. Canonical state lives in `data/state/*.json` + `data/lore/*.md` + git; all writes go through `engine/` → `fs-manager` → `git-sync`. ADR 0001 Phase 1 has shipped: the production backend is **FastAPI** (`backend/main.py`, `backend/routes/*.py`) reading state directly from `data/` — Django has been retired. Postgres keeps running but nothing in the read or write path touches it; Phase 2 (removal) is tracked in `docs/BACKLOG.md`.

Sentinel is a two-node agentic system with a strict filesystem firewall between them. Understanding this split is required before editing anything in `engine/`, `mcp-servers/`, or `schemas/`.

**The two nodes**
- **Inference Node** (`engine/`) — pure-Python package that will house the DM, Fact-Extractor, and Lorekeeper agents. **Never granted direct filesystem access.** Generates narrative, then emits a structured `<world_update>` JSON payload. Currently scaffolding only — the agent entry points raise `NotImplementedError`; `backend/api/dm_ai.py` still serves turns until the migration lands. See `engine/README.md` for the boundary contract.
- **Infrastructure Node** (`mcp-servers/` + `infrastructure/`) — PostgreSQL + pgvector + ChromaDB + the Git-backed hybrid filesystem under `data/`. The only path from Inference → disk.

> `world-engine/` is legacy Replit-era scaffolding (prompt YAML stubs only) pending removal. Do not add code under it. The new Inference Node lives in `engine/`.

The two nodes communicate over a Tailscale mesh in production; locally they run side-by-side on the same host.

**The MCP Bridge** — three Python servers, each on a fixed port:
- `fs-manager` (`:8010`) — only thing that writes `data/state/*.json` and `data/lore/*.md`
- `db-vector` (`:8011`) — PostgreSQL queries + ChromaDB vector upserts
- `git-sync`  (`:8012`) — atomic commit after each world update

**The core loop** (see `ARCHITECTURE.md` §7 for the full diagram):
1. Player action → DM agent → narrative text
2. Fact-Extractor parses `<world_update>` tags out of the narrative
3. Payload validated against `schemas/apply_world_update.schema.json` (Draft 2020-12). **Invalid payloads are rejected and fed back to the DM** — schema failure is a first-class control-flow path, not an error case.
4. Router dispatches to fs-manager / db-vector / git-sync
5. Lorekeeper re-queries ChromaDB and injects fresh context into the next DM turn

**Hybrid storage under `data/`** — human-readable Markdown for lore, machine-readable JSON for state, everything under git. Namespace separation is enforced at write time by fs-manager:
- `data/{lore,state}/core/` — Core team only; writes require a `"namespace": "core"` authorization token
- `data/{lore,state}/community/<pack>/` — community packs, additive only
- Protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`, `core_faction_id`) are immutable to community payloads — enforced via `x-sentinel-protected: true` in the JSON schemas. See `ARCHITECTURE.md` §4.

**Backend** — `backend/` is a FastAPI app on `:8001`. It serves three endpoints (`GET /healthz`, `POST /api/session/new`, `POST /api/stream`), reads state from `data/state/*.json` directly, calls `engine/` for turn handling, and dispatches writes through `engine.apply_world_update` → fs-manager. No ORM, no Django, no Postgres queries. The retired Django backend and Express dev reference lived at `backend/{sentinel,api}/` and `artifacts/api-server/` historically — both are gone as of ADR 0001 Phase 1.

**Frontend** — `apps/sentinel-ui/` (`@sentinel/ui`), React 19 + Vite + Tailwind v4. Connects to Django via fetch-based SSE. Remember: the 1.0 frontend strategy is undecided — do not build new frontend features without explicit direction (see rules above).

**Shared DB schema** — `lib/db/` (Drizzle ORM) is the single source of truth for the PostgreSQL schema. Both the Express reference backend and the Django production backend consume it (Django via `managed=False` models). Schema changes happen in `lib/db/` first.

**Polyglot tooling**
- pnpm workspace (Node 24, pnpm 10) — `pnpm-workspace.yaml` covers `apps/*`, `artifacts/*`, `lib/*`
- Python 3.11+ for the three MCP servers and the Django backend — each MCP server has its own `requirements.txt`
- `chezmoi` generates `infrastructure/.env` from `.chezmoi/dot_infrastructure/dot_env.tmpl` — that's why `just env` exists, and why you should never hand-write `infrastructure/.env`

**Cross-OS constraint** — this project targets macOS, Linux, and Windows. The chezmoi template handles OS-specific values (Docker socket path, Python binary). Never write linux-only shell in a `justfile` recipe without providing the equivalent for other platforms.
