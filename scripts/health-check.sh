#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Project Sentinel — Health Check Script
#
# Lightweight, read-only status check for the full cloud stack.
# Exits 0 if all services are healthy, 1 otherwise.
#
# Usage:
#   bash scripts/health-check.sh
# -----------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

PASS=0
FAIL=0

check() {
  local label="$1"
  local status="$2"  # "ok" or anything else
  local detail="${3:-}"

  if [[ "$status" == "ok" ]]; then
    echo -e "  ${GREEN}✅${RESET}  $(printf '%-22s' "$label") ${detail}"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}❌${RESET}  $(printf '%-22s' "$label") ${detail}"
    FAIL=$((FAIL + 1))
  fi
}

http_check() {
  local url="$1"
  if curl -sf --max-time 3 "$url" > /dev/null 2>&1; then
    echo "ok"
  else
    echo "fail"
  fi
}

docker_health() {
  local container="$1"
  docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not_found"
}

echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Project Sentinel — Stack Health Check${RESET}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# Docker check availability
if ! command -v docker &> /dev/null || ! docker info &> /dev/null 2>&1; then
  echo -e "  ${YELLOW}⚠${RESET}   Docker not available — skipping container checks"
else
  # ChromaDB
  chroma_status=$(docker_health "sentinel-chromadb")
  chroma_http=$(http_check "http://127.0.0.1:8000/api/v1/heartbeat")
  if [[ "$chroma_status" == "healthy" && "$chroma_http" == "ok" ]]; then
    check "ChromaDB" "ok" "127.0.0.1:8000  (container: $chroma_status)"
  else
    check "ChromaDB" "fail" "127.0.0.1:8000  (container: $chroma_status, http: $chroma_http)"
  fi
fi

echo ""

# MCP servers
for server_port in "fs-manager:8010" "git-sync:8012"; do
  name="${server_port%%:*}"
  port="${server_port##*:}"
  result=$(http_check "http://127.0.0.1:${port}/health")
  [[ "$result" == "ok" ]] \
    && check "$name" "ok" "127.0.0.1:${port}" \
    || check "$name" "fail" "127.0.0.1:${port}  (not responding)"
done

echo ""

# Git repository
remote=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "none")
branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
uncommitted=$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
ahead=$(git -C "$REPO_ROOT" rev-list --count "@{u}..HEAD" 2>/dev/null || echo "?")

[[ "$remote" != "none" ]] \
  && check "Git remote" "ok" "$remote" \
  || check "Git remote" "fail" "no remote configured"

[[ -n "$branch" && "$branch" != "unknown" ]] \
  && check "Branch" "ok" "$branch" \
  || check "Branch" "fail" "unknown"

[[ "$uncommitted" == "0" ]] \
  && check "Working tree" "ok" "clean" \
  || check "Working tree" "fail" "$uncommitted uncommitted file(s)"

[[ "$ahead" == "0" || "$ahead" == "?" ]] \
  && check "Remote sync" "ok" "up to date (ahead: ${ahead})" \
  || check "Remote sync" "fail" "${ahead} commit(s) not pushed"

# Summary
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
total=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}  All $total checks passed.${RESET}"
  exit_code=0
else
  echo -e "${RED}${BOLD}  $FAIL/$total checks failed.${RESET} Run 'bash scripts/start-cloud.sh' to bring up missing services."
  exit_code=1
fi
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

exit $exit_code
