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

### Building the closed alpha site

The public closed alpha lives at `sentinel.russalo.com/alpha/` (decided
2026-06-06). Unlike the tailnet dev site (served at the hostname root), the
alpha mounts under the `/alpha/` path prefix — the hostname root is reserved
for a future landing page and returns 404 today.

```bash
pnpm --filter @sentinel/ui build:alpha
```

`build:alpha` is a script alias for `vite build --mode alpha`, which loads
`apps/sentinel-ui/.env.alpha` (`VITE_API_URL=/alpha/api`) and triggers the
conditional `base: '/alpha/'` in `vite.config.js`. The output `dist/`:

- emits asset URLs prefixed `/alpha/...`
- wires Wouter's Router base to `/alpha` (read from `import.meta.env.BASE_URL`
  in `App.jsx` — single source of truth, no parallel constant to drift)
- targets the same-origin relative API path `/alpha/api/...`

The closed alpha is deployed **gate-fronted, not direct-to-origin-core**
(decided 2026-06-06, same shape as `blog.russalo.com`). DNS for
`sentinel.russalo.com` resolves to a separate **gate** machine (tailnet
Claude's lane) that owns DNS, TLS provisioning, and TLS termination. Gate
reverse-proxies cleartext HTTP over tailnet to origin-core's Caddy, which
runs the committed template (`infrastructure/caddy/Caddyfile.example`).
Origin-core's Caddy is multi-tenant (serves blog + Blueprint + sentinel on
a shared wildcard `:80` listener); listener isolation between public and
tailnet is enforced at the UFW firewall layer, NOT by `bind` in the Caddy
site block — adding `bind` to one site-block would shadow the wildcard
listener for the others. Inside the site block, our template owns the
sentinel-specific shape: `basic_auth` invite gate, `handle_path /alpha/*`,
the SPA fallback, and the static-asset cache headers. `handle_errors`
(operational, deploy-only) is hoisted to site-block scope in the deployed
Caddyfile (Caddy 2.x rejects nesting inside `handle_path`) — non-alpha
paths already 404, so the friendly error page only fires for the alpha
block. The template's leading comment documents these deployed-Caddyfile
gotchas surfaced during the 2026-06-07 cutover.

Caddy strips the `/alpha` prefix at origin-core (`handle_path /alpha/*`)
before reverse-proxy, so the backend stays mounted at `/api/...` unchanged
and the file_server reads `dist/assets/...` unchanged. The two builds —
`pnpm build` for the tailnet dev site (no prefix) and `pnpm build:alpha`
for the alpha (with prefix) — produce different `dist/` outputs; switching
deployments requires the matching build.

**Operational note for the backend env:** with gate fronting, set
`SENTINEL_TRUSTED_PROXY_HOPS=1` in `infrastructure/.env` so the per-IP
rate-limiter counts the real client IP (one hop in: gate). Without it, gate
gets one shared bucket for every alpha tester.

The default `pnpm build` flow for the tailnet dev site is unchanged.

See `CLAUDE.md` § "Common Commands" for the full reference.

### Alpha deployment (staging → production) — RFC-0015

**The alpha is NOT deployed by building into `dist/`.** Per RFC-0015, origin-core's
Caddy roots `/alpha/` at a serve tree *outside* the code repo, so a build never
touches the live path:

```
/srv/serve/sentinel-alpha/          # SENTINEL_ALPHA_SERVE_ROOT (default)
  releases/<git-sha>/               # each = one build:alpha output, immutable
  current  -> releases/<sha>        # what production serves
  staging  -> releases/<sha>        # what the staging URL serves (the candidate)
```

Deploy is three deliberate steps, all from `master` in a patch window:

```bash
# 1. Build a release into the serve tree + point `staging` at it (no prod change).
just build-alpha-release
#    Refuses off master / on a dirty tree. Byte-faithful to `build:alpha`.

# 2. Verify the candidate in a real browser at the tailnet-only staging host:
#    https://sentinel-staging.dev.russalo.com/alpha/
#    (no blank page; assets /alpha/-prefixed; the actual change works).

# 3. Promote — atomically repoint `current` at the verified release (zero downtime).
just promote-alpha
```

- **Rollback:** `just rollback-alpha` repoints `current` at the previous release.
- **Inspect:** `just alpha-status` shows current / staging / previous + releases.
- **Prune:** `just prune-alpha-releases [keep=5]` (never deletes current/staging).

The staging host serves the same `/alpha/*` shape as prod (`/alpha/api → :8001`,
same `/alpha` strip), rooted at `staging` — so the *same build bytes* verify on
staging and promote to prod. It runs the candidate **frontend against the prod
backend** (`:8001`) this slice; a staging-own backend is a future slice.

**Frontend/backend coupling:** when a release depends on new backend behavior
(e.g. an RFC-0014 field), deploy the **backend first** (`systemctl restart
sentinel-backend`), then `build-alpha-release` → verify → promote — the staging
step is where a frontend/backend mismatch gets caught before prod.

**Lane split:** Sentinel owns the serve tree contents (releases / the symlinks /
the promote) and these recipes; tailnet owns the edge — Caddy rooting `/alpha/` at
`current`, the staging host, and the invite gate. See
`infrastructure/caddy/Caddyfile.example` (SERVE MODEL note) and RFC-0015.

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

**Arming is host-gated by a marker file (PR #156), not a hand-edit.** A host with
a `~/.sentinel-armed` marker renders the armed config from the chezmoi template's
armed branch on `just env`: `SENTINEL_WORLDS_ROOT` (a path outside this repo —
`$HOME/sentinel-worlds`), the `SENTINEL_RL_*` / `SENTINEL_LLM_DAILY_CEILING` /
`SENTINEL_MAX_CONCURRENT_STREAMS` knobs, `SENTINEL_TRUSTED_PROXY_HOPS=1`, the
feedback knobs, and the **age-decrypted** `SENTINEL_SESSION_TOKEN_SECRET`.
Unmarked hosts (dev / CI / fresh clone) render dormant defaults (shared tree,
anonymous, unthrottled, Groq). The marker is host-local + uncommitted, so a clone
never self-arms, and it gates *render* time — so `just env` is the pickup step no
matter how services are supervised. (It's used instead of `.chezmoi.hostname`,
which resolves to `srv334254` on origin-core via Hostinger's `/etc/hosts` stamp —
that would silently disarm the alpha.) For the age key / recipient / custody /
rotation substrate, see **`SECRET-MANAGEMENT.md` in the `russalo/tailnet` repo**
(the shared secret store — a separate private repo, same owner; intentionally not
duplicated here per the doc-split). This doc owns only the sentinel-side marker +
`just env` + service flow.

All three services read `SENTINEL_WORLDS_ROOT` independently — the **backend**
(`backend/config.py` → `worlds_root`, routes reads) and **fs-manager** +
**git-sync** (`mcp-servers/*/server.py` → `WORLDS_ROOT`, route writes/commits) —
so **all three must agree** (a split writes state to the wrong tree). On
origin-core they run as **systemd units** (`infrastructure/systemd/*.service`,
`User=<USER>`) that each load the same rendered `infrastructure/.env` via
`EnvironmentFile=`, so one `just env` feeds all three uniformly. Agreement is
**enforced**: the backend **refuses to start** in per-world mode unless both MCP
`/health` report `worlds_root: true` (`backend/mcp_agreement.py`), and
`just cutover-check` surfaces the same — plus env, bind, and rate-limit posture —
*before* a restart.

**Cutover / re-cutover checklist (origin-core):**

1. Tracer-soak (`tests/test_world_isolation_tracer_soak.py`) is green in CI.
2. Arm + render: `touch ~/.sentinel-armed`, then `just env`. Renders the full
   armed `infrastructure/.env` at mode 0600 (the source is `private_`), including
   the age-decrypted session secret. (Requires the shared age key at
   `~/.config/chezmoi/key.txt` — an armed host without it fails the render *loud*
   rather than blanking auth; key custody is in `SECRET-MANAGEMENT.md` in the
   `russalo/tailnet` repo.)
   `SENTINEL_ALLOW_PUBLIC_BIND` stays unset (not in the template).
3. Caddy: `caddy hash-password` → put the hash in `$SENTINEL_INVITE_HASH`; apply
   `infrastructure/caddy/Caddyfile.example` to the live Caddyfile; `caddy reload`.
4. Restart the MCP servers so they pick up the rendered `.env`:
   `sudo systemctl restart sentinel-fs-manager sentinel-git-sync`.
5. **`just cutover-check`** — the go/no-go gate. Must report **READY** (no FAILs).
6. Restart the backend: `sudo systemctl restart sentinel-backend`; its startup
   agreement check re-confirms per-world mode, then it serves.

**First-time install of the systemd units** (one-time, needs root — done on
origin-core 2026-06-25): substitute `<REPO_ROOT>` / `<USER>` in
`infrastructure/systemd/*.service`, `sudo cp` them to `/etc/systemd/system/`,
`sudo systemctl daemon-reload`, then `sudo systemctl enable --now
sentinel-fs-manager sentinel-git-sync` and (once they're up) `sudo systemctl
enable --now sentinel-backend`. systemd reads `EnvironmentFile=` as root *before*
dropping to `User=`, so the 0600 `.env` needs no loosening. Before the migration,
free the ports by stopping any prior nohup processes.

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
overwritten on the next stack start. (An *armed* host — one with a
`~/.sentinel-armed` marker — is the opposite: there `just env` renders the armed
value into `.env` from the template's armed branch, and the systemd units load it
via `EnvironmentFile=`; a shell `export` wouldn't reach systemd-managed services.
An unmarked dev box gets the blank default, which is why the shell-export approach
here is the right move for dev.) For local dev, the shell env is the durable
single source that every consumer reads:

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
