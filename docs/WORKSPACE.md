# Workspace — Project Sentinel

Developer context document. Covers stack, structure, data storage, AI
architecture, and API routes for contributors and AI coding agents.

_Last updated: 2026-06-05_

---

## Overview

pnpm workspace monorepo. The frontend is JavaScript/React (JSX); the backend,
engine, and MCP servers are Python.

This is an **AI-powered RPG World Engine** — a fully automated, persistent
RPG interface where an AI Dungeon Master narrates the world and automatically
updates world state (characters, locations, factions, items) after each player
turn. Canonical state lives on disk as JSON and Markdown under `data/`, version-
controlled by git. No database in the turn loop.

_Previously: Express 5 API server, PostgreSQL + Drizzle ORM. Both retired in
ADR 0001 Phases 1–2 (2026-04-13). The old `artifacts/api-server/` and `lib/`
packages are gone._

---

## Stack

| Concern | Choice | Notes |
|---|---|---|
| Monorepo | pnpm workspaces | `apps/*`, `scripts` |
| Node.js | 24 | |
| Package manager | pnpm 10 | |
| Frontend | React 19 + Vite + Tailwind v3 | `apps/sentinel-ui/` (`@sentinel/ui`) |
| Styling | Tailwind CSS v3 | Custom design tokens (void, amber, codex…) |
| State | Zustand | 5 stores: world, chat, player, ui, persona |
| Routing | Wouter | Client-side: `/` (WorldList), `/create`, `/w/:worldId`, `/data` |
| Backend | FastAPI | `backend/` — port `:8001` |
| AI / Inference | Python engine package | `engine/` — DM agent + Fact-Extractor |
| LLM endpoint | OpenAI-compatible (`OPENAI_BASE_URL`) | Currently Groq (`llama-3.3-70b-versatile`); any OpenAI-compatible API (LiteLLM / Ollama / OpenAI) works |
| MCP servers | Python / FastAPI | `mcp-servers/fs-manager` (`:8010`), `mcp-servers/git-sync` (`:8012`) |
| Vector store | ChromaDB | Docker; reserved for future Lorekeeper RAG |
| Python | 3.11+ | Backend, engine, MCP servers |
| Schema validation | JSON Schema Draft 2020-12 + jsonschema | `schemas/apply_world_update.schema.json` |
| Command runner | `just` | Cross-OS; all recipes in `justfile` |
| Env generation | chezmoi | OS-aware `infrastructure/.env` |

---

## Structure

```text
project-sentinel/
├── apps/
│   └── sentinel-ui/        # React 19 + Vite frontend (@sentinel/ui)
├── backend/                # FastAPI app — :8001 (session, stream, healthz)
├── engine/                 # Pure-Python Inference Node package
│   └── agents/             # dm.py, fact_extractor.py (lorekeeper planned, not yet created)
├── mcp-servers/
│   ├── fs-manager/         # Writes data/state/*.json and data/lore/*.md — :8010
│   └── git-sync/           # Atomic git commit after each world update — :8012
├── data/
│   ├── state/core/         # Machine-readable JSON world state (entities, sessions…)
│   └── lore/core/          # Human-readable Markdown lore + presets (TOML)
├── schemas/                # Shared JSON Schema contracts
├── infrastructure/         # Docker Compose + chezmoi .env template
├── scripts/                # Shell automation
├── tests/                  # pytest suites (Python)
├── docs/                   # BACKLOG, ROADMAP, VISION, ADRs, QUICKSTART
├── justfile                # All dev recipes — run `just` for the list
└── pnpm-workspace.yaml
```

---

## Data Storage

No database. Per **ADR 0001**, `data/` is the canonical source of truth:

| Path | Contents |
|---|---|
| `data/state/core/entities/` | Character, NPC, enemy JSON files |
| `data/state/core/locations/` | Location JSON files |
| `data/state/core/factions/` | Faction JSON files |
| `data/state/core/items/` | Item JSON files |
| `data/state/core/world/state.json` | Global world state (location, tension, weather, time) |
| `data/state/core/sessions/<uuid>.json` | Per-session turn log |
| `data/lore/core/` | Markdown lore, session logs, preset TOML files |

All writes go through `engine/` → `fs-manager` → `git-sync`. The backend
never writes to `data/` directly. Every world update produces a git commit
via `git-sync`, giving a full per-turn audit trail.

---

## AI Architecture

### Two-node model

- **Inference Node** (`engine/`) — pure Python, never touches the filesystem.
  Runs the DM and Fact-Extractor agents; emits structured `<world_update>` JSON.
- **Infrastructure Node** (`mcp-servers/` + `data/`) — the only path from the
  Inference Node to disk. Schema-gates every write.

### Engine agents (`engine/agents/`)

| Agent | File | Status |
|---|---|---|
| DM | `dm.py` | Live — `run_turn`, `stream_turn`, `generate_intro` |
| Fact-Extractor | `fact_extractor.py` | Live — `extract` parses `<world_update>` tags |
| Lorekeeper | _(planned)_ | Not yet created — ChromaDB RAG, unscheduled |

### Turn loop

1. Player action → `engine.agents.dm` → narrative text + `<world_update>` block
2. `engine.agents.fact_extractor` parses the block into an `apply_world_update` payload
3. Payload validated against `schemas/apply_world_update.schema.json`
   — invalid payloads are **rejected and fed back to the DM**, not silently dropped
4. Dispatcher calls `fs-manager` to apply state changes, then `git-sync` to commit
5. Next turn reads `data/state/*.json` directly (no cache layer)

### Preset content (`data/lore/core/presets/`)

TOML files for genres, personas, moods, and regions. `backend/presets.py`
loads them at session-create time; `engine/agents/dm.py` injects the resolved
fragments into the DM system prompt as a "WORLD FOUNDATIONS" block.

---

## API Routes (`backend/`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Health check |
| `POST` | `/api/session/new` | Start a new session — loads presets, calls DM intro, dispatches seed entities |
| `POST` | `/api/stream` | Submit a player turn — SSE stream of DM tokens + `world_update` event |
| `GET` | `/api/world/{world_id}` | Resume hydration — the world's session + world state |
| `GET` | `/api/worlds` | List existing worlds (the "my worlds" picker) |
| `DELETE` | `/api/world/{world_id}` | Hard-delete a world (teardown) |
| `GET` | `/api/sessions`, `/api/sessions/{id}`, `/api/sessions/{id}/export` | Recorded-session training browser (the `/data` page) |

---

## Frontend Pages (`apps/sentinel-ui/`)

| Route | Page | Description |
|---|---|---|
| `/` | `WorldList` | "My worlds" picker — lists existing worlds + entry to create |
| `/create` | `WorldCreation` | Pre-game form: genre, tone, region, persona, mood, modifiers |
| `/w/:worldId` | `AppShell` | Game shell: responsive 3-panel layout (panels hidden on mobile, accessible via drawer) |
| `/data` | `DataBrowser` | Recorded-session training browser |

---

## Development

```bash
just env             # generate infrastructure/.env for your OS
just install         # pnpm install + all Python deps

just dev             # frontend + backend together
just dev-frontend    # Vite dev server only
just dev-backend     # FastAPI on :8001 only

just test            # Python schema tests + all JS tests
just build           # pnpm build across workspace
just build-site      # frontend → dist/ for the tailnet dev site
just typecheck       # pnpm typecheck (no emit)

just start           # full stack: Docker → MCP servers
just health          # pass/fail table for every service

just export-training-data  # recorded sessions → datasets/ (schema + chatlogs)
just observe-datasets      # file-observer manifest of the chatlog corpus
```

## Training-data pipeline

Mock human+AI sessions recorded through the normal play loop become training
data via two steps (both write to the gitignored `datasets/`):

1. **`just export-training-data`** — reads `data/state/core/sessions/*.json` and
   writes `datasets/schema/*.jsonl` (narrative→`apply_world_update` recognition
   examples) + `datasets/chatlogs/*.md` (speaker-labelled transcripts).
2. **`just observe-datasets`** — runs [file-observer](https://pypi.org/project/file-observer/)
   (`fo`) over `datasets/chatlogs/` and writes a deterministic manifest + report
   to `datasets/observed/` (chatlog detection, author/structure signals) to
   characterize the corpus before external training. Requires `pip install
   file-observer`.

## Building the dev site

The tailnet dev site at `sentinel.dev.russalo.com` is served by Caddy on
`origin-core`: `/api/*` and `/healthz` reverse-proxy to the FastAPI backend on
`127.0.0.1:8001`; everything else is static files from
`apps/sentinel-ui/dist/`. Run `just build-site` to (re)generate that `dist/`.

> **MCP network-isolation invariant (ADR 0003 §3).** Caddy proxies **only** the
> backend. It must **never** proxy the MCP servers `fs-manager` (`:8010`) or
> `git-sync` (`:8012`) — they are the unauthenticated write layer and their
> safety is topology (loopback/tailnet only). As a backstop, both servers
> default to `127.0.0.1` and **refuse an all-interfaces bind** (`0.0.0.0`/`::`)
> unless `SENTINEL_ALLOW_PUBLIC_BIND=1` is set. Don't set that, and don't add a
> Caddy route to `:8010`/`:8012`.

The frontend reads its API base from `VITE_API_URL`, baked in at build time.
`apps/sentinel-ui/.env.production` (committed — the URL is public, not secret)
pins it to `https://sentinel.dev.russalo.com/api` so the served UI calls the
same origin (Caddy proxies `/api/*` to the backend) rather than the visitor's
own `localhost`. A local `just dev-frontend` ignores this — it uses the
`http://localhost:8001/api` fallback in `src/api/client.js`.

See `CLAUDE.md` § "Common Commands" for the full reference.

## Production deployment (origin-core) — ADR 0003 Slice C

Templates live in `infrastructure/`; the live config is applied by hand on
`origin-core` (Linux). All of this is **opt-in** — a local `just start` / `just
dev` setup needs none of it.

**1. systemd units** (`infrastructure/systemd/*.service`) run the backend and
both MCP servers as services that survive reboot. Each is a template — replace
`<REPO_ROOT>` and `<USER>`, copy to `/etc/systemd/system/`, then
`systemctl daemon-reload && systemctl enable --now sentinel-{fs-manager,git-sync,backend}`.
The backend unit is ordered `After=`/`Wants=` the two MCP units so its startup
config-agreement check (per-world mode) finds them up; if it races ahead before
they're listening, `Restart=on-failure` retries — no corruption. They load
`infrastructure/.env`, so the cutover vars below propagate to all three.
(systemd is Linux-only; dev on macOS/Windows keeps `just start`.)

**2. Caddy invite gate** (`infrastructure/caddy/Caddyfile.example`, ADR 0003
§1) — a single shared `basic_auth` credential gates the SPA and `/api/*`;
`/healthz` stays open for monitoring. So only invited testers reach the backend
or spend LLM calls; rotate the bcrypt hash to revoke everyone. Apply:

```bash
caddy hash-password                       # → bcrypt hash for the shared invite pw
# put the hash in $SENTINEL_INVITE_HASH (env / chezmoi-managed, NEVER committed)
# fill <REPO_ROOT> in the dist root path, then:
caddy reload --config /etc/caddy/Caddyfile
```

Caddy is assumed already system-managed on origin-core (no unit shipped). Per
the isolation invariant above, the Caddyfile proxies **only** `:8001` — never
`:8010`/`:8012` (`tests/test_caddy_invariant.py` guards the template).

Rate-limiting is **not** at the edge (`rate_limit` needs a non-stock Caddy
plugin) — it's in the backend (ADR 0003 Slice B): set `SENTINEL_RL_SESSION_CREATE_PER_HOUR`,
`SENTINEL_RL_STREAM_PER_MINUTE`, `SENTINEL_LLM_DAILY_CEILING` in
`infrastructure/.env`. Per-world session tokens arm with `SENTINEL_SESSION_TOKEN_SECRET`.
Behind Caddy, also set **`SENTINEL_TRUSTED_PROXY_HOPS=1`** so the per-IP limiter
keys on the hop Caddy appends, not a client-spoofable `X-Forwarded-For` (the
default `0` ignores XFF and keys on the socket peer). The Caddy template also
**excludes `/api/sessions*`** from the public edge (the cross-world training
browser stays tailnet-only).

## Per-world isolation cutover (`SENTINEL_WORLDS_ROOT`)

Per [ADR 0002](adr/0002-world-identity-and-isolation.md), each world can live in
its own git repo under `SENTINEL_WORLDS_ROOT` instead of the shared `data/`
tree in this repo. **The env var is unset by default**, so the stack runs on the
single shared tree exactly as before — the per-world routing is built and tested
(the tracer-soak gate in `tests/test_world_isolation_tracer_soak.py` proves zero
cross-world leak) but dormant until you flip it.

**The cutover is one operational change: set `SENTINEL_WORLDS_ROOT` to the same
absolute path for all three services**, since they each read it independently:

- the **backend** (`backend/config.py` → `worlds_root`) — routes reads,
- **fs-manager** and **git-sync** (`mcp-servers/*/server.py` → `WORLDS_ROOT`) —
  route writes/commits.

It belongs in `infrastructure/.env` (the chezmoi template ships the `SENTINEL_*`
knobs defaulted-off — re-run `just env` to pick them up, which also drops any
stale legacy vars from an old generated `.env`), pointing at a data root
**outside this repo** (e.g. `~/sentinel-worlds`). **All three must agree** — a
split (backend per-world but a server still shared, or vice versa) would write
state to the wrong tree. This is now **enforced**: the backend **refuses to
start** in per-world mode unless both MCP `/health` report `worlds_root: true`
(`backend/mcp_agreement.py`), and `just cutover-check` surfaces the same — plus
the env, bind, and rate-limit posture — *before* you restart anything.

**Cutover checklist (origin-core):**

1. Tracer-soak (`tests/test_world_isolation_tracer_soak.py`) is green in CI.
2. In `infrastructure/.env` (chezmoi template → `just env`): set the **same**
   `SENTINEL_WORLDS_ROOT` (absolute path, outside this repo) for all three
   services, plus `SENTINEL_SESSION_TOKEN_SECRET`, the `SENTINEL_RL_*` /
   `SENTINEL_LLM_DAILY_CEILING` knobs, `SENTINEL_MAX_CONCURRENT_STREAMS=10`
   (closed-alpha planning target — caps in-flight `/api/stream` requests;
   503 + `Retry-After: 5` past cap), and `SENTINEL_TRUSTED_PROXY_HOPS=1` (behind
   Caddy). Leave `SENTINEL_ALLOW_PUBLIC_BIND` unset.
3. Caddy: `caddy hash-password` → put the hash in `$SENTINEL_INVITE_HASH`; apply
   `infrastructure/caddy/Caddyfile.example` to the live Caddyfile; `caddy reload`.
4. (Re)start the MCP servers (`systemctl restart sentinel-fs-manager sentinel-git-sync`).
5. **`just cutover-check`** — the go/no-go gate. Must report **READY** (no FAILs).
6. Restart the backend (`systemctl restart sentinel-backend`); its startup
   agreement check re-confirms per-world mode, then it serves.

### Closed-alpha operator dashboard

While the alpha runs, watch live counters at **`http://127.0.0.1:8001/_status`**
(or via tailnet against origin-core's bind). Vanilla-HTML page polling
`/api/admin/status` every 5s — surfaces active streams + cap, 503 capacity
rejects, 429 rate-limit hits, MCP health, settings posture. **Tailnet/loopback
only** — Caddy excludes `/api/admin*` and `/_status` from the public edge by
the same invariant that excludes `/api/sessions*` (operator data; never
reaches an invited tester). `tests/test_caddy_invariant.py` guards this.

For terminal-only ops:
```
curl -s http://127.0.0.1:8001/api/admin/status | jq .
```

Manual spot-check (what `cutover-check` automates): each server's `/health`
must show `"worlds_root": true`:

```
curl -s localhost:8010/health localhost:8012/health   # fs-manager, git-sync
```

Once set, a new world is provisioned automatically: `POST /api/session/new`
mints a `world_id` and calls git-sync's `init_world` (`git init` + baseline +
first commit) before the first write. **No frontend change is required to flip
the cutover** — `/api/stream` locates a turn's world from its `session_id`
(the session is the authoritative routing key), so the client need not send
`world_id`. (Slice 4's `/w/<world_id>` frontend routing is a resume/share UX
nicety, not a cutover prerequisite.) Reset a single world with
`just reset-world --world-id <id>` (reads `$SENTINEL_WORLDS_ROOT`).

Pre-cutover sessions keep working: `find_session_data_dir` scans the per-world
trees first and **falls back to the shared tree**, so a session created before
the flip (its `world_id` is empty, so its writes also go to the shared tree)
still resolves end-to-end. New worlds are isolated; the shared tree acts as
"world zero" for legacy sessions (ADR 0002 § Consequences).

Do **not** flip the cutover unless `tests/test_world_isolation_tracer_soak.py`
is green in CI — it is the isolation gate.

### Local dev: keep gameplay out of the code repo

The same `SENTINEL_WORLDS_ROOT` knob solves a purely-local annoyance: by default,
`git-sync` writes a per-turn `[sentinel] world=… session=… turn=…` commit to the
**checked-out branch** (normally `master`), so playing or recording locally
pollutes `master` and diverges it from origin. Pointing the worlds root outside
the repo eliminates it.

**Set it as a shell environment variable — *not* in `infrastructure/.env`.** That
file is a regenerated artifact (`just env`, and the `env` prerequisite of `just
start`, run `chezmoi apply --force` over it), so a hand-edited value is silently
overwritten on the next stack start. (The production cutover above is the
opposite: there you *do* set it via the template → `.env`, because the systemd
units load `.env` through `EnvironmentFile` and a shell `export` wouldn't reach
them — that path doesn't run `just env` per stack start.) For local dev, the
shell env is the durable single source that every consumer reads:

```
export SENTINEL_WORLDS_ROOT="$HOME/sentinel-worlds"   # a path OUTSIDE this repo
just fs-manager &   # MCP server — reads os.environ directly
just git-sync   &   # MCP server — reads os.environ directly
just dev-backend    # backend — load_dotenv(override=False), so the shell env wins
```

(Leave the access knobs — `SENTINEL_SESSION_TOKEN_SECRET`, the `SENTINEL_RL_*`
limits, `SENTINEL_LLM_DAILY_CEILING` — unset; they're independent of isolation.)

Each world is then its own git repo at `<worlds_root>/<world_id>/`, every per-turn
commit lands **there**, and the code repo is never touched — you can even
play/record on `master` itself. With the same shell env exported,
`just export-training-data` finds the corpus (the script reads
`$SENTINEL_WORLDS_ROOT` and scans every world's sessions).

**Why the individual recipes, not `just start`:** `just start` depends on `env`,
which regenerates `infrastructure/.env` from the template — blanking
`SENTINEL_WORLDS_ROOT` *and* resetting the placeholder Groq key — and
`scripts/start-cloud.sh` then `source`s that regenerated `.env`, clobbering the
value you exported. `just fs-manager` / `just git-sync` do neither: they just run
`server.py`, which reads `os.environ`, so your exported value survives. (You skip
ChromaDB this way, which the turn loop doesn't use.) See `docs/BACKLOG.md` for the
`.env`-loading and placeholder-secret footguns behind this.
