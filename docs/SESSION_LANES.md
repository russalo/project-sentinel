# Session lanes — four Claude sessions on one repo

> **Status: TRIAL** (started 2026-08-17, review ≈ 2026-08-25). Approved by Russell.
> Modeled on TrenchIQ's `docs/SESSION_LANES.md`, cut down to what Sentinel needs.
> If this banner ever says *retired*, the lanes are gone and this file is history.

Sentinel is worked by **one Orchestrator + three lane sessions**, each in its own
git worktree off the same `.git`. Lanes exist so independent work can proceed in
parallel *without* multiplying the review load on the one human reviewer — the
trial's only success metric is whether Russell's review/merge queue felt better.

If you are a lane session: **read this whole file before your first action.** The
rest of `CLAUDE.md` (plan-first, explicit approval, backlog hygiene, DCO) still
binds you in full; this file only adds the boundaries.

## 0. The lanes at a glance

| `app_name` | Worktree | Branches | Owns |
|---|---|---|---|
| `project-sentinel` — **Orchestrator** | `/srv/projects/project-sentinel` | **`master`** — the ONLY tree that may check out, pull, or reset `master` | plan/pace, RFCs/ADRs, `docs/`, `schemas/` (the seam), `infrastructure/`, the 4-leg review swarm, PR merges, every deploy recipe, the live prod + staging stacks, `docs/BACKLOG.md` triage, memory, **all outbound relays** |
| `sentinel-be` | `/srv/projects/sentinel-be` | own `feat/*` / `fix/*` / `chore/*` | `engine/`, `backend/`, `mcp-servers/`, `tests/` |
| `sentinel-fe` | `/srv/projects/sentinel-fe` | own branches | `apps/sentinel-ui/`, `apps/sentinel-site/` (+ their vitest / typecheck) |
| `sentinel-play` | `/srv/projects/sentinel-play` (detached, **read-only**) | none | plays **staging** as a tester; writes reports to `scratch/collab/` — never the repo |

`git worktree list` must show exactly **one** `[master]`, and it must be the
Orchestrator's tree.

## 1. Orchestrator (`project-sentinel`)

Plans and paces, writes briefs, owns the seam and every cross-cutting change,
runs the decorrelated review swarm on *every* lane PR (author ≠ reviewer — a lane
never runs the swarm on its own PR), merges, deploys through the RFC-0015 /
RFC-0016 recipes, and is the **only** session that speaks to peers (blueprint,
tailnet, Blueprint fact-blocks). Anything reaching a peer signed `sentinel-be`,
`sentinel-fe`, or `sentinel-play` is a lane violation — the peer should bounce it
via Russell.

The Orchestrator MUST NOT quietly do lane work to "save a round-trip"; if it
touches `engine/` or `apps/`, it is because the change is cross-lane (see § 4) and
the brief says so.

## 2. Engineering lanes (`sentinel-be`, `sentinel-fe`)

A lane's unit of work is: **read the brief → plan → get Russell's explicit "go"
in the lane's own session → implement on a branch off fresh `master` → run the
lane's own suite + `ruff format` / `ruff check` (be) or vitest + `pnpm typecheck`
(fe) → `git commit -s` → push → `gh pr create` (title/body matched to recent PRs)
→ address PR-bot comments as follow-up commits → tell the Orchestrator the PR is
ready.** Then stop. The Orchestrator swarms, merges, and deploys.

Lanes MUST NOT:

- check out, pull, or `reset` `master` — rebase your branch onto `origin/master`
  (`git fetch && git rebase origin/master`), never touch the ref itself;
- edit `schemas/`, `docs/adr/`, `docs/rfc/`, `infrastructure/`, or `CLAUDE.md`
  without an Orchestrator brief that says so;
- run `just start`, `just env`, `just install` (the `env` prerequisite regenerates
  `infrastructure/.env` in the Orchestrator's tree), any `just *alpha*` /
  `just stage-*` / `just promote-*` recipe, or `systemctl` anything;
- merge a PR, run the review swarm on their own PR, or relay outward;
- **play the game against any stack that lacks `SENTINEL_WORLDS_ROOT`** (§ 3.1).

## 3. Sentinel-specific hazards a lane inherits

### 3.1 ⚠ Worktrees have NO `infrastructure/.env` — so no `SENTINEL_WORLDS_ROOT`

`.env` is gitignored and lives only in the Orchestrator's tree. A backend started
from a lane worktree without `SENTINEL_WORLDS_ROOT` will commit every game turn to
**the lane's feature branch**, and the squash-merge then carries gameplay data
onto `master` (the PR #108 → #110 incident; see the "Squash-merge captures
gameplay state" hunt-list entry in `CLAUDE.md`). Rule: **engineering lanes do not
play.** Verification is pytest / vitest / typecheck. If a lane genuinely needs a
running stack, it uses the isolated **mock-DM** shape (`SENTINEL_DM_MODE=mock`,
`SENTINEL_SKIP_ENV_CHECK=1`, an explicit temp `SENTINEL_WORLDS_ROOT`, alt ports —
§ 3.2) and checks `git log` for `[sentinel] world=…` commits before opening a PR.

### 3.2 Ports are allocated per PROJECT, not per worktree

`8001/8010/8012` (prod) and `8101/8110/8112` (staging) are systemd units running
from the Orchestrator's tree — never bind them from a lane. Lane allocations
(registered in Blueprint):

| Purpose | Port(s) |
|---|---|
| `sentinel-be` ad-hoc mock-DM stack (backend / fs-manager / git-sync) | `8301` / `8310` / `8312` |
| `sentinel-fe` Vite dev server | `5178` (`5173`–`5176` belong to other projects on origin-core) |

Only one `just stage-candidate` may run at a time → Orchestrator-owned.

### 3.3 Per-worktree dependencies

`node_modules` and `.venv` are not shared across worktrees. Each engineering lane
runs `pnpm install` once, and `sentinel-be` runs `just install-backend` so its
`.venv` lands in its own tree (keeps the CI-pinned `ruff` version local to the lane
— see the `project_ci_ruff_pin` memory: CI runs **both** `ruff check` and
`ruff format --check`).

### 3.4 `dist` and the dev site

A raw `pnpm --filter @sentinel/ui build:alpha` in a worktree writes *that
worktree's* `dist` (harmless), but the fe lane still never runs
`just build-alpha-release` (it refuses off-master anyway) — a lane verifies with
vitest + typecheck, not a build.

### 3.5 `docs/BACKLOG.md` is one file

Two lanes appending in the same window will conflict. Lanes append at the **end
of the most specific existing section** only, one entry per discovery, in the
`CLAUDE.md` format; the Orchestrator resolves conflicts at merge and owns triage.

## 4. The seam

What crosses lanes, and therefore belongs to the Orchestrator:

- `schemas/apply_world_update.schema.json` and the fs-manager write boundary;
- the SSE `world_update` **hint** contract, including the explicit-`null`
  deletion markers only the post-#189 `worldStore` deep-merge understands (deploy
  order SPA-first, backend-second follows from this);
- ADR-0004 state-truthfulness work — engine computes → backend injects → SPA
  hint mirror; PR #189 was a be/fe seam bug, which is why these slices stay
  Orchestrator-driven;
- `docs/alpha/TESTER_GUIDE.md` (rendered by both the gated app and the public site).

For any seam change the Orchestrator writes a one-page brief in
`scratch/collab/<lane>-brief.md` (gitignored) *before* the lane starts, naming the
contract on both sides. There is no shared inbox bus in v1 — briefs + direct
session messages are enough for three lanes.

## 5. Play lane (`sentinel-play`)

A tester, not an engineer. It exists because every truthfulness bug of the last
month (HP bar jumping to full, raw `<action>` markup, imposter PCs) was found by
*playing*, and the hunt list's own warning is "biased validation corpus — one
smoke transcript ≠ coverage."

- **Target: staging only** — backend `:8101`, world store `~/sentinel-worlds-staging`,
  real DM through LiteLLM, session tokens armed (carry `X-Sentinel-World-Token`
  from the `/api/session/new` response). Drives turns over the API from a terminal
  (`POST /api/session/new` → `POST /api/stream` SSE); no browser required.
- **Reads** the staging world store after each turn to compare *what the DM
  narrated* against *what was persisted* — ADR-0004's tester, live. Constructs the
  inputs the corpus omits: non-ASCII names, hostile phrasing, level-up spam, death
  sequences, imposter-PC prompts, long sessions.
- **Owns** `scratch/collab/playtest-YYYY-MM-DD.md` (gitignored): reproducible
  transcripts with world id / session id / turn number, and "narrative said X,
  state says Y" findings. The Orchestrator graduates ripe items into
  `docs/ALPHA_FEEDBACK.md` → `docs/BACKLOG.md`.
- **Spend cap: ≤ 40 turns/day** (staging's `SENTINEL_LLM_DAILY_CEILING` is 200;
  the cap leaves room for the deploy gate). If a run needs more, ask.
- **MUST NOT:** edit any repo file (its worktree is detached at `master`, reference
  only), open PRs, touch prod (`:8001` or the alpha URL), deploy, restart units,
  or relay outward.
- Off-server candidate #1 (needs only tailnet reach to `:8101` + read access to the
  staging store — the store is the one thing that keeps it on-box). `sentinel-fe`
  is candidate #2. Trigger to move either: sustained origin-core stress.

## 6. Blueprint / fleet

Four agent rows: `sentinel-claude` (Orchestrator, only relayer), `sentinel-be-claude`,
`sentinel-fe-claude`, `sentinel-play-claude` (lane_kind `app`, `spawn_mode` same-dir,
launched flag-form `claude --remote-control <app_name>` from each worktree).
Edges: `sentinel-play ──tester──▶ project-sentinel`. Ports per § 3.2.

## 7. Trial exit

At ≈ 2026-08-25 Russell picks one: **keep** (this file loses the TRIAL banner),
**shrink** (drop a lane — `git worktree remove`, retire its Blueprint row), or
**fold back** (all three lanes retired; banner → *retired*; this file stays as the
record). Nothing about the live stacks changes in any outcome — no lane ever
deploys, and the trial adds no units, no `.env` edits, no live ports.
