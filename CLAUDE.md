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
- Writing or updating the plan file at `~/.claude/plans/`
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

## Branching and Merging

The default branch is `master`. Never push to `master` directly.

Every unit of work gets its own branch off fresh master, named after
the kind of change it is:

- `feat/<short-description>` — new feature or capability
- `fix/<short-description>` — bug fix or regression
- `chore/<short-description>` — cleanup, deletion, refactor with no
  behavior change
- `docs/<short-description>` — documentation-only change
- `ci/<short-description>` — CI workflow or tooling change

Workflow for each unit of work:

1. `git checkout master && git pull --ff-only`
2. `git checkout -b <prefix>/<short-description>`
3. Make the changes and commit them with DCO sign-off
   (`git commit -s`). Multiple commits are fine; they get squashed
   on merge anyway. `CONTRIBUTING.md` § "DCO Sign-off (Required)"
   is the canonical rule — every commit needs `Signed-off-by:`.
4. Push with `git push -u origin <branch>`
5. Open a PR with `gh pr create` — title + body formatted to match
   recent PRs on this repo
6. Wait for CI; address review-bot comments inline as small followup
   commits on the same branch
7. Squash-merge with `gh pr merge <N> --squash --delete-branch` once
   CI is green and comments are addressed
8. Run `just end-session` before stopping at equilibrium — it
   re-checks the backlog and structure so drift from the PR is
   caught before the session closes. Then stop; don't chain into
   the next unit of work without checking in with the user first.

Multiple logically-separate units of work should go to separate PRs
— but "logically separate" is judged by the user's "solo repo, bigger
swaths OK" preference: a coherent multi-commit sweep is one PR, not
six. Splitting into smaller PRs is only worth it when the split makes
the diff more legible or lets part of the work ship while another
part waits for review.

`tomorrow prep` or `end of day` may involve closing loose ends on
multiple branches; those are the exceptions where multiple PRs
land back-to-back.

---

## Reviewing changes (decorrelated swarm)

For anything cross-cutting (multi-subsystem, public-facing, concurrency),
run a **decorrelated review swarm** — reviewers that fail *differently*, so
each catches what the author (you) and the others miss:

1. **`/code-review master...HEAD`** (in-house) — best at sibling-path
   completeness ("hardened A, missed B/C") and logic. (Default branch is
   `master`; adjust the base if you branched from elsewhere.)
2. **Cross-model (Gemini)** — invoke the `gemini` CLI read-only (`--approval-mode
   plan --skip-trust`) with the diff + a falsify prompt. It reads `GEMINI.md` at
   the repo root for auditor instructions + the hunt list. Best at attacking
   premises a same-model reviewer inherited. Chunk by subsystem; for a sliced
   change, add one **integration pass aimed at the seam** where slices meet.
   *(On origin-core, a ready wrapper — `gem.sh`, flash; fall back from pro on
   "Invalid stream" — lives in the sibling File Observer project at
   `/srv/projects/pkplab/scanner/scratch/review/`; it is external to this repo.)*
3. **PR bots** (Codex / Gemini Code Assist / Copilot) — open a PR. Best at
   doc/code drift after reworks.

Disciplines (more important than the tools): **falsify-first**; treat tests/
corpus as **biased** (construct the input they omit); **triage = verification**
(repro a finding in ~10 lines → real or dropped; act on a reproduction, never on
a tag — bots over-tag and re-flag fixed issues); **convergence across layers =
strongest real-bug signal**; **re-run the full suite + a real-flow check after
every fix round**, gated (cheap suite every round; expensive check at round
boundaries and mandatory before merge — never skipped). Per-PR review + a final
integration pass for sliced features.

### Failure patterns this codebase exhibits (hunt these first)

Seeded from real bugs; update each release. The cross-model auditor's copy lives
in `GEMINI.md`.

- **Inter-world / cross-boundary state bleed** — state/context/RNG/transcript
  leaking across worlds or sessions (shared mutable globals, a fixed path not
  scoped by `world_id`, a cache keyed without the world). This is the
  cross-session contamination that motivated ADR 0002, generalized to the
  multi-tenancy boundary. *Prove it deterministically with a tracer soak — stub
  the DM with a per-world token and assert no cross-world leak; never against a
  live LLM.*
- **Sibling-path incompleteness** — a fix on path A while siblings B/C keep the
  bug (e.g. the `list_sessions`→`get_session` canonical-id miss).
- **Doc/code drift after reworks** — comments/docs/ADRs describing a superseded
  design (engine "scaffolding," Tailwind v4, Express/Django in CONTRIBUTING).
- **Schema-gate bypass** — a write path reaching fs-manager without
  `apply_world_update.schema.json` validation, or treating a rejection as fatal
  instead of feeding it back to the DM.
- **git-sync committing to the checked-out branch** — the `master`-pollution
  hazard during play/recording.
- **Malformed-LLM-output intolerance** — non-`dict` `world_update`, non-`list`
  collections.
- **Path traversal via id interpolation** — `session_id`/`world_id` as path
  components; UUID-validate (`_require_uuid`) before building any path, in the
  backend AND the MCP servers.
- **No cross-process locking** — in-process locks don't serialize backend /
  fs-manager / git-sync.
- **Determinism where it's asserted** — anything claimed deterministic that
  depends on dict/set iteration, time, randomness, or filesystem ordering.
- **Stale-cache-after-redeploy** — a cached `index.html` pointing at a purged
  hashed bundle → blank page.
- **Provider/API param compat** (`max_completion_tokens` vs `max_tokens`);
  **env/setup fragility** (PEP 668, missing venv, bare `pip`/`uvicorn` in
  recipes); **biased validation corpus** (one smoke transcript ≠ coverage).

---

## Directory Conventions

- `docs/` — project documentation (BACKLOG.md, ROADMAP.md, VISION.md, QUICKSTART.md, ADRs)
- `backend/` — FastAPI production backend (`:8001`)
- `engine/` — pure-Python Inference Node package (agents, dispatch, schema)
- `mcp-servers/` — Python MCP server implementations (fs-manager, git-sync)
- `apps/sentinel-ui/` — React 19 + Vite frontend
- `data/` — canonical world state (`state/*.json`) and lore (`lore/*.md`) under git
- `schemas/` — shared JSON Schema contracts
- `infrastructure/` — Docker Compose and environment configuration
- `scripts/` — shell scripts for automation and dev lifecycle
- `tests/` — pytest suites (Python)

---

## Things to Know About This Project

- This is a cross-OS project. Do not write scripts or configs that assume linux-only.
- Replit was the original development platform. Migration is complete.
  Do not introduce new `@replit/*` dependencies.
- **React is the 1.0 frontend.** Decided 2026-04-15 by the landing of
  `feat/panel-ux-entity-cards` — the "undecided, do not build new
  frontend features" gate that previously lived here is resolved. See
  `docs/VISION.md` § "Resolved decisions" for the rationale. Frontend
  work is a normal feature-work pathway; the usual "plan-then-execute,
  wait for explicit approval" flow still applies like it does for any
  other task, but there's no longer a special stack-decision gate.
- `just` is the command runner. Add new recipes to `justfile` rather than creating
  standalone scripts unless the logic is complex enough to warrant a separate file.
- **Local play/smoke sessions commit to the checked-out branch.** The
  engine's `git-sync` writes a per-turn
  `[sentinel] world=… session=… turn=…` commit (the `world=` prefix since
  ADR 0002 Slice 1 threads a per-session `world_id`) to whatever branch is
  checked out — normally `master` — on every turn. Running a playthrough locally therefore pollutes `master` and
  diverges it from origin (this is exactly what produced the 22 stray
  commits cleaned up on 2026-05-30). Run play/smoke sessions on a
  throwaway branch, or reset/clean up afterward, and never push those
  auto-commits. The `just reset-world` and smoke-harness items in
  `docs/BACKLOG.md` are the durable fix.

---

## Planning Docs: Near-Term vs Vision

Every planning document in this repo must explicitly separate **near-term target**
from **vision target**. The split is structural — either two files or two clearly
labeled sections — never blended into prose.

- **Near-term target** — what ships in the next 1–3 PRs. Concrete, linked to
  `docs/BACKLOG.md` IDs, stack and architecture assumed fixed. This is a
  commitment, not a wishlist.
- **Vision target** — what Sentinel points at beyond the near-term. Aspirational,
  open questions allowed, stack choices explicitly up for debate. This is a
  direction, not a plan.

**Two files vs one file with two sections:**
- Use **two files** when the vision has enough surface area to rot slower than
  execution (e.g. `docs/ROADMAP.md` and a separate `docs/VISION.md`, or
  `docs/FRONTEND_PLAN.md` and a separate stack-decision note). Add a one-line
  pointer from each to the other.
- Use **one file with two labeled sections** when the topic is small enough to
  stay coherent (e.g. `docs/TESTING.md` with "Current" and "Vision" sections).

When writing a new planning doc, default to this split without being asked.
When revising an existing planning doc that blends the two, flag it and propose
the separation before editing.

---

## Common Commands

`just` is the entry point for everything. `just` with no args lists all recipes.

**Setup**
- `just env` — regenerate `infrastructure/.env` from the chezmoi template (OS-aware: Docker socket path, Python binary)
- `just install` — one-stop installer: pnpm workspace + all Python deps (MCP servers, FastAPI backend, engine package, pytest). Fresh clone should be runnable after `just env && just install`.
- `just install-backend` — reinstall the FastAPI backend's Python deps alone

**Run the stack**
- `just start` — full stack: Docker (ChromaDB) → wait healthy → both MCP servers in background
- `just health` — pass/fail table for every service; exits non-zero if anything is down
- `just reset` — wipe Docker volumes and restart from scratch
- `just up` / `just down` / `just down-volumes` / `just ps` / `just logs [service]` — raw Docker Compose passthroughs
- `just fs-manager` / `just git-sync` — run an individual MCP server in verbose dev mode (ports 8010 / 8012)

**Dev servers**
- `just dev-backend` — FastAPI backend on `:8001` (`uvicorn backend.main:app --reload`)
- `just dev-frontend` — `apps/sentinel-ui` Vite dev server
- `just dev` — frontend + backend together

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

> **Canonical state lives on disk.** Per **[ADR 0001](docs/adr/0001-data-canonical-source-of-truth.md)**, `data/state/*.json` + `data/lore/*.md` + git is the single source of truth. All writes go through `engine/` → `fs-manager` → `git-sync`. Phase 1 replaced Django with FastAPI; Phase 2 removed Postgres from the stack entirely. No database queries in the turn loop.

Sentinel is a two-node agentic system with a strict filesystem firewall between them. Understanding this split is required before editing anything in `engine/`, `mcp-servers/`, or `schemas/`.

**The two nodes**
- **Inference Node** (`engine/`) — pure-Python package housing the DM and Fact-Extractor agents (the Lorekeeper is planned, not yet built — see `docs/BACKLOG.md`). **Never granted direct filesystem access.** Generates narrative, then emits a structured `<world_update>` JSON payload. Live and wired into the FastAPI backend; the engine→fs-manager→git-sync path runs end-to-end. See `engine/README.md` for the boundary contract.
- **Infrastructure Node** (`mcp-servers/` + `infrastructure/`) — ChromaDB (for future RAG / Lorekeeper) + the git-backed hybrid filesystem under `data/`. The only path from Inference → disk.

The two nodes communicate over a Tailscale mesh in production; locally they run side-by-side on the same host.

**The MCP Bridge** — two Python servers, each on a fixed port:
- `fs-manager` (`:8010`) — only thing that writes `data/state/*.json` and `data/lore/*.md`
- `git-sync`  (`:8012`) — atomic commit after each world update

**The core loop** (see `ARCHITECTURE.md` for the full diagram):
1. Player action → DM agent → narrative text
2. Fact-Extractor parses `<world_update>` tags out of the narrative
3. Payload validated against `schemas/apply_world_update.schema.json` (Draft 2020-12). **Invalid payloads are rejected and fed back to the DM** — schema failure is a first-class control-flow path, not an error case.
4. Dispatcher calls fs-manager to apply state changes, then git-sync to commit
5. Next turn reads the updated `data/state/*.json` directly (no cache layer)

**Hybrid storage under `data/`** — human-readable Markdown for lore, machine-readable JSON for state, everything under git. Namespace separation is enforced at write time by fs-manager:
- `data/{lore,state}/core/` — Core team only; writes require a `"namespace": "core"` authorization token
- `data/{lore,state}/community/<pack>/` — community packs, additive only
- Protected fields (`unique_id`, `world_seed`, `namespace`, `created_at`, `canon`, `core_faction_id`) are immutable to community payloads — enforced via `x-sentinel-protected: true` in the JSON schemas.

**Backend** — `backend/` is a FastAPI app on `:8001`. It serves `GET /healthz`, `POST /api/session/new`, and `POST /api/stream` (SSE). It reads state from `data/state/*.json` directly, calls `engine/` for turn handling, and dispatches writes through `engine.apply_world_update` → fs-manager → git-sync. No ORM, no database queries. Per **[ADR 0002](docs/adr/0002-world-identity-and-isolation.md)**, every session is minted a `world_id` (UUID) that is threaded through both dispatch calls; when `SENTINEL_WORLDS_ROOT` is set, the MCP servers route to a per-world `data/` tree / git repo under it. The env var is **unset by default** (per-world routing dormant; single shared tree) until the ADR 0002 Slice 3 cutover.

**Frontend** — `apps/sentinel-ui/` (`@sentinel/ui`), React 19 + Vite + Tailwind v3. Talks to the FastAPI backend via fetch + SSE. React is the ratified 1.0 frontend stack as of 2026-04-15 (see `docs/VISION.md` § "Resolved decisions"); normal feature-work rules apply.

**Polyglot tooling**
- pnpm workspace (Node 24, pnpm 10) — `pnpm-workspace.yaml` covers `apps/*` and `scripts`
- Python 3.11+ for the MCP servers, the FastAPI backend, and the engine package — each has its own `requirements.txt`
- `chezmoi` generates `infrastructure/.env` from `.chezmoi/dot_infrastructure/dot_env.tmpl` — that's why `just env` exists, and why you should never hand-write `infrastructure/.env`

**Cross-OS constraint** — this project targets macOS, Linux, and Windows. The chezmoi template handles OS-specific values (Docker socket path, Python binary). Never write linux-only shell in a `justfile` recipe without providing the equivalent for other platforms.
