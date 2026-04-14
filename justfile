# Project Sentinel — Command Runner
# https://github.com/casey/just
#
# Install:
#   macOS/Linux:  brew install just
#   Cargo:        cargo install just
#   Windows:      winget install Casey.Just
#   Ubuntu/Debian: apt install just
#
# Usage: just <recipe>   •   just --list

# Show all available recipes (default when you run `just` with no args)
default:
    @just --list --unsorted

# ─── Setup ────────────────────────────────────────────────────────────────────

# Generate infrastructure/.env from the OS-aware chezmoi template
env:
    chezmoi apply --source .chezmoi --destination . --force

# Install all dependencies: Node packages (pnpm) + Python MCP servers + FastAPI backend + engine + tests
install: env
    pnpm install --frozen-lockfile
    pip install -q -r mcp-servers/fs-manager/requirements.txt
    pip install -q -r mcp-servers/db-vector/requirements.txt
    pip install -q -r mcp-servers/git-sync/requirements.txt
    pip install -q -r backend/requirements.txt
    pip install -q -r engine/requirements.txt
    pip install -q -r tests/requirements.txt

# ─── Cloud Environment ────────────────────────────────────────────────────────

# Spin up the full cloud stack: Docker → PostgreSQL + ChromaDB → all MCP servers
start: env
    bash scripts/start-cloud.sh

# Wipe Docker volumes and restart from scratch
reset:
    bash scripts/start-cloud.sh --reset

# Check health of all running services (exits 1 if anything is down)
health:
    bash scripts/health-check.sh

# ─── Docker ───────────────────────────────────────────────────────────────────

# Start infrastructure containers (PostgreSQL + ChromaDB)
up:
    cd infrastructure && docker compose up -d

# Stop infrastructure containers (data is preserved)
down:
    cd infrastructure && docker compose down

# Stop containers AND wipe all persistent volumes (full reset)
down-volumes:
    cd infrastructure && docker compose down -v

# Show container status
ps:
    cd infrastructure && docker compose ps

# Tail container logs; optionally pass a service name: just logs postgres
logs service="":
    cd infrastructure && docker compose logs -f {{ service }}

# ─── MCP Servers (individual, dev mode) ───────────────────────────────────────

# Start the filesystem manager MCP server on :8010 (verbose dev mode)
fs-manager:
    python3 mcp-servers/fs-manager/server.py --port 8010 --dev

# Start the vector DB interface MCP server on :8011 (verbose dev mode)
db-vector:
    python3 mcp-servers/db-vector/server.py --port 8011 --dev

# Start the git-sync MCP server on :8012 (verbose dev mode)
git-sync:
    python3 mcp-servers/git-sync/server.py --port 8012 --dev

# ─── Build & Type Checks ──────────────────────────────────────────────────────

# Full TypeScript build + typecheck for all workspace packages
build:
    pnpm build

# TypeScript typecheck only (no emit)
typecheck:
    pnpm typecheck

# ─── Local Dev ────────────────────────────────────────────────────────────────

# Start the Sentinel UI frontend dev server (apps/sentinel-ui)
dev-frontend:
    pnpm --filter @sentinel/ui run dev

# Start the FastAPI backend on :8001 (per ADR 0001 Phase 1)
dev-backend:
    uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload

# Install backend Python dependencies (FastAPI stack)
install-backend:
    pip install -r backend/requirements.txt

# Start both frontend and backend together
dev:
    just dev-backend & just dev-frontend

# ─── Tests ────────────────────────────────────────────────────────────────────

# Run Python schema validation tests
test-schemas:
    pytest tests/

# Run all tests: schema validation + TypeScript test suites
test: test-schemas
    pnpm -r --if-present run test

# ─── Claude Code Integration ──────────────────────────────────────────────────

# Copy the current Claude Code session transcript into chatlogs/.
# Invoked automatically by the PreCompact hook in .claude/settings.json
# before Claude Code compacts the context window, so the full
# unabridged session JSONL is preserved locally before it's lost.
# Also runnable manually to snapshot the current conversation.
# Cross-OS: delegates to a Python script that parses the hook's
# JSON-on-stdin contract and anchors output to $CLAUDE_PROJECT_DIR.
capture-transcript:
    python3 scripts/capture-transcript.py

# ─── Session Lifecycle ────────────────────────────────────────────────────────

# Fetch latest, show branch status, open backlog items, and verify structure
start-session:
    git fetch origin
    @echo ""
    @echo "=== Branch Status ==="
    git status --short --branch
    @echo ""
    @echo "=== Open Backlog Items ==="
    bash scripts/backlog.sh list
    @echo ""
    @just check-structure

# Remind about open backlog + structure drift before closing
end-session:
    @echo "=== Open Backlog Items ==="
    bash scripts/backlog.sh list
    @echo ""
    @just check-structure
    @echo ""
    @echo "Reminder: commit, push, and update BACKLOG.md before closing."

# Verify all documented directories and files exist on disk
check-structure:
    bash scripts/check-structure.sh

# ─── Git Hooks ────────────────────────────────────────────────────────────────

# Post-merge hook: reinstall locked deps + apply DB migrations
post-merge:
    pnpm install --frozen-lockfile
    pnpm --filter db push
