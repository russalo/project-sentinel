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

# Python interpreter name. Cross-OS: Windows installers typically
# expose `python`, while macOS/Linux expose `python3` (and often
# both). Overridable via the PYTHON_BIN environment variable for
# unusual setups (e.g. pyenv shims, virtualenvs). Used by every
# recipe that invokes a Python script directly.
default_python_bin := if os_family() == "windows" { "python" } else { "python3" }
python_bin := env_var_or_default("PYTHON_BIN", default_python_bin)

# Interpreter for backend/server recipes. Prefer the repo-root `.venv` (created
# during setup) so these recipes work without manually activating it — the
# fragility that made `just dev-backend` fail with `uvicorn: not found` from a
# non-activated shell. Cross-OS: `.venv/bin` on macOS/Linux, `.venv/Scripts` on
# Windows. Falls back to python_bin when no venv exists. A PYTHON_BIN override
# still wins (it takes precedence over venv autodetection).
venv_python := \
    if env_var_or_default("PYTHON_BIN", "") != "" { python_bin } \
    else if path_exists(".venv/bin/python") == "true" { ".venv/bin/python" } \
    else if path_exists(".venv/Scripts/python.exe") == "true" { ".venv/Scripts/python.exe" } \
    else { python_bin }

# Serve tree for the closed-alpha frontend deploy pipeline (RFC-0015). The
# build→stage→promote recipes manage releases/ + the current/staging symlinks
# inside it; Caddy roots /alpha/ at `<root>/current` (a symlink), never at
# apps/sentinel-ui/dist. Default is the origin-core path tailnet provisions
# (russellp-owned, outside the code repo); overridable for other hosts.
alpha_serve_root := env_var_or_default("SENTINEL_ALPHA_SERVE_ROOT", "/srv/serve/sentinel-alpha")

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
    pip install -q -r mcp-servers/git-sync/requirements.txt
    pip install -q -r backend/requirements.txt
    pip install -q -r engine/requirements.txt
    pip install -q -r tests/requirements.txt

# ─── Cloud Environment ────────────────────────────────────────────────────────

# Spin up the full cloud stack: Docker → ChromaDB → all MCP servers
start: env
    bash scripts/start-cloud.sh

# Wipe Docker volumes and restart from scratch
reset:
    bash scripts/start-cloud.sh --reset

# Check health of all running services (exits 1 if anything is down)
health:
    bash scripts/health-check.sh

# Pre-cutover readiness check (ADR 0002/0003) — READ-ONLY; exits 1 if NOT ready.
# Run before flipping the per-world + public cutover (see docs/WORKSPACE.md).
cutover-check:
    "{{ python_bin }}" scripts/cutover-check.py

# Concurrent-streams load smoke against a live backend — N worlds × M turns.
# Each turn is a real LLM call (costs money). Refuses to run unless
# SENTINEL_WORLDS_ROOT is set (else per-turn commits pollute the checked-out
# branch); pass extra args after `--`: `just load-smoke -- --concurrent 5 --turns 3`.
# Exits: 0=healthy 1=degraded 2=broken 3=setup-error 4=LLM-provider-rate-limited.
# See docs/TESTING.md.
load-smoke *FLAGS:
    "{{ venv_python }}" scripts/load-smoke.py {{ FLAGS }}

# ─── Docker ───────────────────────────────────────────────────────────────────

# Start infrastructure containers (ChromaDB)
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
    "{{ python_bin }}" mcp-servers/fs-manager/server.py --port 8010 --dev

# Start the git-sync MCP server on :8012 (verbose dev mode)
git-sync:
    "{{ python_bin }}" mcp-servers/git-sync/server.py --port 8012 --dev

# ─── Build & Type Checks ──────────────────────────────────────────────────────

# Full TypeScript build + typecheck for all workspace packages
build:
    pnpm build

# Build the frontend for the tailnet dev site → apps/sentinel-ui/dist (served by
# Caddy at sentinel.dev.russalo.com). Production mode bakes VITE_API_URL from
# apps/sentinel-ui/.env.production so the served UI calls the same origin.
build-site:
    pnpm --filter @sentinel/ui build

# ─── Alpha deploy pipeline (RFC-0015) ─────────────────────────────────────────
# dev → staging → production for the closed-alpha frontend. Caddy roots /alpha/
# at {{ alpha_serve_root }}/current (a symlink), so a build NEVER touches the
# live-served path. These are deploy-host (origin-core) recipes — they need the
# serve tree and GNU coreutils. Full runbook: docs/WORKSPACE.md § "Alpha
# deployment (staging → production)". build-alpha-release is byte-faithful to
# `build:alpha` (same `vite build --mode alpha`, different outDir), so it never
# writes apps/sentinel-ui/dist; it refuses on a dirty tree or off master.

# Build an alpha release into the serve tree and point staging at it (no promote).
build-alpha-release:
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{ alpha_serve_root }}"
    branch="$(git rev-parse --abbrev-ref HEAD)"
    [ "$branch" = "master" ] || { echo "refusing: on '$branch' — deploy from master only" >&2; exit 1; }
    [ -z "$(git status --porcelain)" ] || { echo "refusing: working tree is dirty" >&2; exit 1; }
    [ -d "$root" ] || { echo "serve tree $root missing (RFC-0015 provisioning)" >&2; exit 1; }
    sha="$(git rev-parse --short HEAD)"
    dest="$root/releases/$sha"
    tmp="$root/releases/.tmp-$sha.$$"
    mkdir -p "$root/releases"
    rm -rf "$tmp"
    echo "▶ building alpha release $sha"
    pnpm --filter @sentinel/ui exec vite build --mode alpha --outDir "$tmp" --emptyOutDir
    # A real alpha build has /alpha/-prefixed asset refs; guard against a stray
    # base='/' build (the class of bug this pipeline exists to stop).
    grep -q 'src="/alpha/assets/' "$tmp/index.html" || { echo "refusing: built index.html is not /alpha/-based" >&2; rm -rf "$tmp"; exit 1; }
    rm -rf "$dest"
    mv "$tmp" "$dest"
    ln -sfn "releases/$sha" "$root/staging"
    echo "✓ staged: $root/staging → releases/$sha"
    echo "  verify → https://sentinel-staging.dev.russalo.com/alpha/   then: just promote-alpha"

# Promote the staging release to production (atomic current repoint; records previous).
promote-alpha:
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{ alpha_serve_root }}"
    [ -L "$root/staging" ] || { echo "no staging release — run just build-alpha-release" >&2; exit 1; }
    target="$(readlink "$root/staging")"
    [ -d "$root/$target" ] || { echo "staging target $target missing" >&2; exit 1; }
    if [ -L "$root/current" ]; then readlink "$root/current" > "$root/.previous"; fi
    ln -sfn "$target" "$root/.current.new"
    mv -Tf "$root/.current.new" "$root/current"
    echo "✓ promoted: current → $target  (previous: $(cat "$root/.previous" 2>/dev/null || echo none))"
    echo "  rollback: just rollback-alpha"

# Roll production back to the previously-promoted release (reversible).
rollback-alpha:
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{ alpha_serve_root }}"
    [ -f "$root/.previous" ] || { echo "no previous release recorded" >&2; exit 1; }
    prev="$(cat "$root/.previous")"
    [ -d "$root/$prev" ] || { echo "previous release $prev is gone (pruned?)" >&2; exit 1; }
    cur="$(readlink "$root/current" 2>/dev/null || echo none)"
    ln -sfn "$prev" "$root/.current.new"
    mv -Tf "$root/.current.new" "$root/current"
    printf '%s\n' "$cur" > "$root/.previous"
    echo "✓ rolled back: current → $prev  (was $cur)"

# Show the alpha serve tree state (current / staging / previous + releases).
alpha-status:
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{ alpha_serve_root }}"
    [ -d "$root" ] || { echo "serve tree $root missing" >&2; exit 1; }
    echo "current  → $(readlink "$root/current" 2>/dev/null || echo '(none)')"
    echo "staging  → $(readlink "$root/staging" 2>/dev/null || echo '(none)')"
    echo "previous : $(cat "$root/.previous" 2>/dev/null || echo '(none)')"
    echo "releases (newest first):"
    ls -1dt "$root"/releases/*/ 2>/dev/null | sed 's#/*$##; s#.*/#  #' || echo "  (none)"

# Prune old releases, keeping the newest N (default 5); never deletes current/staging.
prune-alpha-releases keep="5":
    #!/usr/bin/env bash
    set -euo pipefail
    root="{{ alpha_serve_root }}"
    keep="{{ keep }}"
    cd "$root/releases"
    protected="$(for l in current staging; do readlink "$root/$l" 2>/dev/null | sed 's:.*/::'; done | sort -u)"
    kept=0
    for d in $(ls -1dt */ 2>/dev/null | sed 's:/*$::'); do
      if printf '%s\n' "$protected" | grep -qx "$d"; then echo "keep (in use): $d"; continue; fi
      kept=$((kept + 1))
      if [ "$kept" -le "$keep" ]; then echo "keep: $d"; else echo "prune: $d"; rm -rf -- "$d"; fi
    done

# Export recorded mock sessions → datasets/ (schema JSONL + raw chatlogs).
# Schema examples train narrative→world_update recognition; chatlogs are
# file-observer-detectable transcripts. Needs the backend Python env active.
export-training-data:
    "{{ python_bin }}" scripts/export_training_data.py

# Observe the exported chatlog corpus with file-observer → a deterministic
# manifest + report under datasets/observed/ (chatlog detection, author /
# structure signals) to characterize the corpus before external training.
# Requires `pip install file-observer`. Run `just export-training-data` first.
observe-datasets:
    fo datasets/chatlogs --specialists -o datasets/observed

# TypeScript typecheck only (no emit)
typecheck:
    pnpm typecheck

# ─── Local Dev ────────────────────────────────────────────────────────────────

# Start the Sentinel UI frontend dev server (apps/sentinel-ui)
dev-frontend:
    pnpm --filter @sentinel/ui run dev

# Start the FastAPI backend on :8001 (per ADR 0001 Phase 1)
# Runs uvicorn as a module under venv_python so it works whether or not the venv
# is activated — bare `uvicorn` only resolves on PATH inside an activated venv.
dev-backend:
    "{{ venv_python }}" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload --no-proxy-headers

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
    "{{ python_bin }}" scripts/capture-transcript.py

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

# Reset world state to an empty baseline for an isolated smoke-test run (flags: --snapshot NAME, --no-commit)
reset-world *args:
    "{{ python_bin }}" scripts/reset-world.py {{ args }}

# ─── Git Hooks ────────────────────────────────────────────────────────────────

# Post-merge hook: reinstall locked deps
post-merge:
    pnpm install --frozen-lockfile
