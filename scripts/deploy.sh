#!/usr/bin/env bash
# Runs ON the deploy server (invoked by the GitHub Actions deploy job after it
# git-resets the checkout to origin/main, or manually for a first/emergency
# deploy). Rebuilds the stack in place and gates on the health endpoint.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f infra/docker-compose.yml"

# Host port comes from infra/.env on the server (shared box: 6 teams)
HTTP_PORT=$(grep -E '^YADRO_HTTP_PORT=' infra/.env 2>/dev/null | cut -d= -f2 || true)
HTTP_PORT="${HTTP_PORT:-8080}"

echo "» building + starting stack (http port ${HTTP_PORT})"
$COMPOSE up -d --build

echo "» waiting for health"
for _ in $(seq 1 36); do
  if curl -sf "http://localhost:${HTTP_PORT}/api/health" >/dev/null 2>&1; then
    echo "» healthy"
    $COMPOSE ps
    # shared disk hygiene: drop dangling layers from the rebuild
    docker image prune -f >/dev/null
    echo "OK — deployed $(git rev-parse --short HEAD)"
    exit 0
  fi
  sleep 5
done

echo "!! health check failed after 3 minutes" >&2
$COMPOSE ps >&2
$COMPOSE logs --tail 50 backend >&2
exit 1
