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
  "mcp-servers/db-vector"
  "mcp-servers/git-sync"
  "infrastructure"
  "schemas"
  "world-engine"
  "apps/sentinel-ui"
  "artifacts/api-server"
  "backend"
  "backend/api"
  "backend/sentinel"
  "engine"
  "engine/agents"
  "engine/prompts"
  "lib/db"
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
  "backend/manage.py"
  "backend/sentinel/settings.py"
  "backend/sentinel/urls.py"
  "backend/api/views.py"
  "backend/api/urls.py"
  "engine/__init__.py"
  "engine/types.py"
  "engine/schema.py"
  "engine/requirements.txt"
  "docs/adr/README.md"
  "docs/adr/0001-data-canonical-source-of-truth.md"
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
