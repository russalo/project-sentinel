#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Project Sentinel — Structure Check
#
# Verifies that all documented directories and files actually exist
# on disk. Run this when you suspect docs have drifted from reality,
# or at session start/end via:
#
#   just check-structure
#
# Exits 0 if all paths present.
# Exits 1 with a list of missing paths if any are missing.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Directories that must exist (documented in README.md, ARCHITECTURE.md,
# folder_structure.json, or CLAUDE.md)
DIRS=(
  "data/lore"
  "data/state"
  "mcp-servers/fs-manager"
  "mcp-servers/git-sync"
  "infrastructure"
  "schemas"
  "apps/sentinel-ui"
  "backend"
  "backend/routes"
  "backend/state"
  "engine"
  "engine/agents"
  "engine/dispatch"
  "engine/prompts"
  "docs"
  "docs/adr"
  ".chezmoi"
)

# Files that must exist
FILES=(
  "docs/BACKLOG.md"
  "infrastructure/docker-compose.yml"
  "folder_structure.json"
  "justfile"
  "backend/requirements.txt"
  "backend/main.py"
  "backend/config.py"
  "backend/schemas.py"
  "backend/engine_bridge.py"
  "backend/routes/health.py"
  "backend/routes/session.py"
  "backend/routes/stream.py"
  "backend/state/world_context.py"
  "backend/state/sessions.py"
  "engine/__init__.py"
  "engine/types.py"
  "engine/schema.py"
  "engine/requirements.txt"
  "engine/dispatch/__init__.py"
  "engine/dispatch/fs_manager.py"
  "engine/dispatch/git_sync.py"
  "docs/adr/README.md"
  "docs/adr/0001-data-canonical-source-of-truth.md"
  "scripts/capture-transcript.py"
  ".claude/settings.json"
)

MISSING=()

for d in "${DIRS[@]}"; do
  if [[ ! -d "$REPO_ROOT/$d" ]]; then
    MISSING+=("DIR  $d")
  fi
done

for f in "${FILES[@]}"; do
  if [[ ! -f "$REPO_ROOT/$f" ]]; then
    MISSING+=("FILE $f")
  fi
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
  echo "All documented paths present."
  exit 0
else
  echo "MISSING paths (update docs or restore directories):"
  for item in "${MISSING[@]}"; do
    echo "  - $item"
  done
  exit 1
fi
