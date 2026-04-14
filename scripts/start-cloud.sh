#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Project Sentinel — Cloud Environment Startup Script
#
# Spins up the full Infrastructure Node stack:
#   • PostgreSQL 16  (Docker)
#   • ChromaDB       (Docker)
#   • fs-manager MCP server  (:8010)
#   • git-sync   MCP server  (:8012)
#
# Usage:
#   bash scripts/start-cloud.sh          # normal startup
#   bash scripts/start-cloud.sh --reset  # wipe Docker volumes + restart
#
# Logs:
#   /tmp/sentinel-fs-manager.log
#   /tmp/sentinel-git-sync.log
# -----------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infrastructure"
MCP_DIR="$REPO_ROOT/mcp-servers"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✅${RESET} $*"; }
fail() { echo -e "  ${RED}❌${RESET} $*"; }
info() { echo -e "  ${CYAN}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }

banner() {
  echo ""
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}  Project Sentinel — Cloud Environment Startup${RESET}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

wait_for_http() {
  local url="$1"
  local label="$2"
  local max_attempts="${3:-30}"
  local attempt=0

  while [[ $attempt -lt $max_attempts ]]; do
    if curl -sf "$url" > /dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  return 1
}

wait_for_docker_healthy() {
  local container="$1"
  local max_attempts="${2:-60}"
  local attempt=0

  while [[ $attempt -lt $max_attempts ]]; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not_found")
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  return 1
}

kill_mcp_servers() {
  for port in 8010 8012; do
    local pid
    pid=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------

preflight() {
  echo -e "${BOLD}[1/6] Pre-flight checks${RESET}"

  if ! command -v docker &> /dev/null; then
    fail "Docker not found — install Docker Desktop or Docker Engine first"
    exit 1
  fi
  ok "Docker available: $(docker --version | head -1)"

  if ! docker info &> /dev/null; then
    fail "Docker daemon is not running — start Docker and retry"
    exit 1
  fi
  ok "Docker daemon running"

  if ! command -v python3 &> /dev/null; then
    fail "python3 not found — install Python 3.11+"
    exit 1
  fi
  ok "Python available: $(python3 --version)"

  if ! command -v curl &> /dev/null; then
    fail "curl not found — required for health checks"
    exit 1
  fi
  ok "curl available"
}

# -----------------------------------------------------------------------------
# Environment setup
# -----------------------------------------------------------------------------

setup_env() {
  echo ""
  echo -e "${BOLD}[2/6] Environment configuration${RESET}"

  if [[ ! -f "$INFRA_DIR/.env" ]]; then
    info "No .env found — generating from .env.example"
    cp "$INFRA_DIR/.env.example" "$INFRA_DIR/.env"
    # Set a default dev password so docker-compose doesn't fail
    sed -i 's/POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD/POSTGRES_PASSWORD=sentinel_dev_local/' \
      "$INFRA_DIR/.env"
    warn "Generated dev .env with default password. Edit infrastructure/.env before production use."
  fi
  ok "infrastructure/.env ready"
}

# -----------------------------------------------------------------------------
# Node dependencies
# -----------------------------------------------------------------------------

install_node_deps() {
  echo ""
  echo -e "${BOLD}[3/6] Node dependencies (pnpm)${RESET}"

  if command -v pnpm &> /dev/null; then
    info "Running pnpm install..."
    (cd "$REPO_ROOT" && pnpm install --frozen-lockfile 2>&1 | tail -3) || \
      warn "pnpm install reported warnings (non-fatal)"
    ok "Node dependencies installed"
  else
    warn "pnpm not found — skipping Node deps (TypeScript artifacts won't build)"
  fi
}

# -----------------------------------------------------------------------------
# Python dependencies
# -----------------------------------------------------------------------------

install_python_deps() {
  echo ""
  echo -e "${BOLD}[4/6] Python dependencies (MCP servers)${RESET}"

  for server in fs-manager git-sync; do
    local req="$MCP_DIR/$server/requirements.txt"
    if [[ -f "$req" ]]; then
      info "Installing $server deps..."
      pip install -q -r "$req" 2>&1 | tail -2 || {
        fail "$server: pip install failed"
        exit 1
      }
      ok "$server dependencies installed"
    else
      warn "$server: requirements.txt not found — skipping"
    fi
  done
}

# -----------------------------------------------------------------------------
# Docker infrastructure
# -----------------------------------------------------------------------------

start_docker() {
  echo ""
  echo -e "${BOLD}[5/6] Docker infrastructure (PostgreSQL + ChromaDB)${RESET}"

  if [[ "${1:-}" == "--reset" ]]; then
    warn "Reset flag set — bringing down containers and wiping volumes"
    (cd "$INFRA_DIR" && docker compose down -v 2>/dev/null || true)
  fi

  info "Starting containers..."
  (cd "$INFRA_DIR" && docker compose up -d)

  info "Waiting for sentinel-postgres to become healthy (up to 60s)..."
  if wait_for_docker_healthy "sentinel-postgres" 60; then
    ok "PostgreSQL healthy"
  else
    fail "PostgreSQL did not become healthy in 60s — check: docker compose logs postgres"
    exit 1
  fi

  info "Waiting for sentinel-chromadb to become healthy (up to 60s)..."
  if wait_for_docker_healthy "sentinel-chromadb" 60; then
    ok "ChromaDB healthy"
  else
    fail "ChromaDB did not become healthy in 60s — check: docker compose logs chromadb"
    exit 1
  fi
}

# -----------------------------------------------------------------------------
# MCP servers
# -----------------------------------------------------------------------------

start_mcp_servers() {
  echo ""
  echo -e "${BOLD}[6/6] MCP servers${RESET}"

  # Kill any previously running MCP servers on our ports
  kill_mcp_servers

  # Load env vars for MCP servers
  if [[ -f "$INFRA_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$INFRA_DIR/.env"
    set +a
  fi

  # fs-manager :8010
  info "Starting fs-manager on :8010..."
  python3 "$MCP_DIR/fs-manager/server.py" --port 8010 \
    > /tmp/sentinel-fs-manager.log 2>&1 &
  echo $! > /tmp/sentinel-fs-manager.pid

  # git-sync :8012
  info "Starting git-sync on :8012..."
  python3 "$MCP_DIR/git-sync/server.py" --port 8012 \
    > /tmp/sentinel-git-sync.log 2>&1 &
  echo $! > /tmp/sentinel-git-sync.pid

  # Wait for each server
  for server_port in "fs-manager:8010" "git-sync:8012"; do
    local name="${server_port%%:*}"
    local port="${server_port##*:}"
    info "Waiting for $name (:$port)..."
    if wait_for_http "http://127.0.0.1:${port}/health" "$name" 30; then
      ok "$name responding on :$port"
    else
      fail "$name did not start in 30s — check /tmp/sentinel-${name}.log"
      exit 1
    fi
  done
}

# -----------------------------------------------------------------------------
# Status report
# -----------------------------------------------------------------------------

status_report() {
  echo ""
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${BOLD}  Cloud Environment Status${RESET}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""

  # Docker
  local pg_status chroma_status
  pg_status=$(docker inspect --format='{{.State.Health.Status}}' sentinel-postgres 2>/dev/null || echo "unknown")
  chroma_status=$(docker inspect --format='{{.State.Health.Status}}' sentinel-chromadb 2>/dev/null || echo "unknown")
  [[ "$pg_status" == "healthy" ]] && ok "PostgreSQL     healthy at 127.0.0.1:5432" || fail "PostgreSQL     $pg_status"
  [[ "$chroma_status" == "healthy" ]] && ok "ChromaDB       healthy at 127.0.0.1:8000" || fail "ChromaDB       $chroma_status"

  # MCP servers
  for server_port in "fs-manager:8010" "git-sync:8012"; do
    local name="${server_port%%:*}"
    local port="${server_port##*:}"
    if curl -sf "http://127.0.0.1:${port}/health" > /dev/null 2>&1; then
      ok "${name}    healthy at 127.0.0.1:${port}"
    else
      fail "${name}    not responding on :${port}"
    fi
  done

  # Git
  echo ""
  local remote branch clean
  remote=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "none")
  branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  clean=$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  ok "Git remote     $remote"
  ok "Branch         $branch"
  [[ "$clean" == "0" ]] && ok "Working tree   clean" || warn "Working tree   $clean uncommitted file(s)"

  echo ""
  echo -e "${BOLD}  Logs${RESET}"
  info "fs-manager → /tmp/sentinel-fs-manager.log"
  info "git-sync   → /tmp/sentinel-git-sync.log"
  echo ""
  echo -e "${GREEN}${BOLD}  All systems up. Project Sentinel is live.${RESET}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

banner
preflight
setup_env
install_node_deps
install_python_deps
start_docker "${1:-}"
start_mcp_servers
status_report
