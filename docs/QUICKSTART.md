# Project Sentinel — Zero to Hero in 5 Minutes

Welcome, Technician. This guide gets the **Infrastructure Node** running on your local machine and proves — with a live API call — that the schema-enforcement layer actually works. No Tailscale required for local development.

> **What you'll have at the end:** A running ChromaDB vector store and a live MCP server that validates AI-generated world updates against a JSON Schema contract before touching a single file.

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| [Docker](https://docs.docker.com/get-docker/) + Docker Compose | Latest | Runs the ChromaDB container |
| [Python](https://www.python.org/downloads/) | **3.11+** | Runs the MCP servers (strict type hints require 3.11) |
| [just](https://github.com/casey/just) | 1.x | Cross-OS command runner — `brew install just` · `cargo install just` · `winget install Casey.Just` |
| [chezmoi](https://www.chezmoi.io/) | 2.x | OS-aware `.env` generation — `brew install chezmoi` · `sh -c "$(curl -fsLS get.chezmoi.io)"` |
| [Git](https://git-scm.com/) | Any | Clones the repo |
| [Tailscale](https://tailscale.com/download) | Any | **Optional** — only needed for multi-machine deployments |

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/russalo/project-sentinel.git project-sentinel
cd project-sentinel
```

> **Why this is cool:** The repo is a pnpm monorepo with a React frontend and Python MCP servers living side by side. You only need Python for the Infrastructure Node — the frontend is a separate concern you can ignore entirely to start.

---

## Step 2: Configure Your Environment

```bash
just env
```

Chezmoi reads `.chezmoi/dot_infrastructure/dot_env.tmpl` and writes
`infrastructure/.env` with the correct settings for your OS — including a
commented-out `DOCKER_HOST` line for macOS Docker Desktop and a `PYTHON_BIN`
hint for Windows.

> **Why this is cool:** The `TAILSCALE_BIND_IP` variable means the same template
> works for both local dev (`127.0.0.1`) and a real multi-node mesh deployment
> (a Tailscale IP like `100.x.y.z`). Zero config drift between environments.

---

## Step 3: Boot the Infrastructure Node

```bash
just up
```

Verify the ChromaDB container is healthy:

```bash
just ps
```

Expected output — showing **healthy**:

```
NAME                  STATUS
sentinel-chromadb     Up (healthy)
```

If it's still starting up, wait 20 seconds and check again. You can also
hit ChromaDB's heartbeat directly:

```bash
curl http://127.0.0.1:8000/api/v1/heartbeat
# Expected: {"nanosecond heartbeat": <timestamp>}
```

> **Why this is cool:** Canonical world state lives on disk as JSON and
> Markdown under `data/` (per ADR 0001), version-controlled by git. ChromaDB
> is the semantic memory for the future Lorekeeper agent — it will let the
> DM search through thousands of Markdown lore entries by *meaning*, not
> just keywords. No database queries in the turn loop; the filesystem is
> the truth.

---

## Step 4: Start the fs-manager MCP Server

Open a new terminal tab and run:

```bash
just fs-manager
```

This installs the Python deps (if needed) and starts the server with verbose
`--dev` logging so you can see every validation decision in real time.

Expected output:

```
INFO  Starting fs-manager on 127.0.0.1:8010
INFO  Application startup complete.
```

Confirm it's alive:

```bash
curl http://127.0.0.1:8010/health
# Expected: {"status":"ok","server":"fs-manager","version":"0.1.0"}
```

> **Why this is cool:** This server is the entire security boundary between the
> LLM and your filesystem. The AI *never* gets a shell. It can only call this
> validated API. Every write is gated by a JSON Schema contract before any file
> is touched.

---

## Step 5: Hello World — Prove the Schema Gate Works

Two API calls. One succeeds, one gets rejected instantly. Both are educational.

### ✅ Valid World Update

```bash
curl -s -X POST http://127.0.0.1:8010/tools/apply_world_update \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "log_entry": "The adventurer Kael steps into the torch-lit tavern of Trog, scanning for familiar faces among the evening crowd.",
    "updates": [
      {
        "target_file": "data/state/core/entities/kael.json",
        "operation": "create",
        "data": {
          "name": "Kael",
          "location": "Trog Tavern",
          "status": "active"
        }
      }
    ],
    "metadata": {
      "agent": "fact-extractor",
      "turn_number": 1,
      "confidence": 0.95
    }
  }' | python3 -m json.tool
```

Expected response:

```json
{
  "success": true,
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "results": [
    {
      "status": "created",
      "path": "data/state/core/entities/kael.json"
    }
  ]
}
```

Verify both files appeared on disk:

```bash
# The entity state file:
cat data/state/core/entities/kael.json

# The auto-appended session log:
cat data/lore/core/sessions/123e4567-e89b-12d3-a456-426614174000.md
```

Both were written atomically by the MCP server. The Inference Node never touched the filesystem directly.

---

### ❌ Malformed Payload — Watch the Airlock Reject It

```bash
curl -s -X POST http://127.0.0.1:8010/tools/apply_world_update \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "not-a-valid-uuid",
    "log_entry": "Hi",
    "updates": []
  }' | python3 -m json.tool
```

Expected response (HTTP 422):

```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "detail": "'not-a-valid-uuid' is not a 'uuid'",
    "path": ["session_id"]
  }
}
```

> **Why this matters:** This payload has three violations simultaneously — `session_id` is not a UUID, `log_entry` is under the 10-character minimum, and `updates` is empty (minimum 1 item). The schema validator catches all of this *before a single file is opened*. Malformed AI output cannot corrupt world state.

---

## You're In. What's Next?

| Want to... | Go here |
|---|---|
| Understand the full two-node architecture | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Add lore, schemas, or MCP tools | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Run the React frontend | [`apps/sentinel-ui/`](../apps/sentinel-ui/) — `just dev-frontend` |
| Start the git-sync MCP server | `mcp-servers/git-sync/` — `just git-sync` |
| See what ships next vs. the long-term vision | [`docs/ROADMAP.md`](./ROADMAP.md) · [`docs/VISION.md`](./VISION.md) |
| Export a world state as a `.spak` package | `ARCHITECTURE.md` → Sentinel Porter section |

---

*Questions? Open an issue using the [Technician template](../.github/ISSUE_TEMPLATE/mcp_tool.md).*
