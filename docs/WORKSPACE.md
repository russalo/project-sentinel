# Workspace — Project Sentinel

Developer context document. Covers stack, structure, data storage, AI
architecture, and API routes for contributors and AI coding agents.

_Last updated: 2026-05-30_

---

## Overview

pnpm workspace monorepo. The frontend is TypeScript/React; the backend,
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
| Routing | Wouter | Client-side, `/create` + `/` |
| Backend | FastAPI | `backend/` — port `:8001` |
| AI / Inference | Python engine package | `engine/` — DM agent + Fact-Extractor |
| LLM proxy | LiteLLM | Model-agnostic; tested against Ollama locally |
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
│   └── agents/             # dm.py, fact_extractor.py (lorekeeper.py stubbed)
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
| Lorekeeper | `lorekeeper.py` | Stubbed — ChromaDB RAG, unscheduled |

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

---

## Frontend Pages (`apps/sentinel-ui/`)

| Route | Page | Description |
|---|---|---|
| `/create` | `WorldCreation` | Pre-game form: genre, tone, region, persona, mood, modifiers |
| `/` | `AppShell` | Game shell: responsive 3-panel layout (panels hidden on mobile, accessible via drawer) |

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
just typecheck       # pnpm typecheck (no emit)

just start           # full stack: Docker → MCP servers
just health          # pass/fail table for every service
```

See `CLAUDE.md` § "Common Commands" for the full reference.
