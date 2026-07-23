#!/usr/bin/env bash
# Runs ON the deploy server (invoked by the GitHub Actions deploy job after it
# git-resets the checkout to origin/main, or manually for a first/emergency
# deploy). Rebuilds the stack in place and gates on the health endpoint.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f infra/docker-compose.yml -f infra/docker-compose.gpu.yml"

# Host port comes from infra/.env on the server (shared box: 6 teams)
HTTP_PORT=$(grep -E '^YADRO_HTTP_PORT=' infra/.env 2>/dev/null | cut -d= -f2 || true)
HTTP_PORT="${HTTP_PORT:-8080}"

echo "» building images"
# --profile warmup: profiled services are SKIPPED by a plain `compose build`,
# which would leave the warmup gate running a stale image forever.
$COMPOSE --profile warmup build

# Model gate BEFORE the old, working workers are replaced: a warm /hf cache
# passes offline in ~a minute (no token use); a cold cache fails the offline
# attempt fast and the fallback run downloads with HF_TOKEN from infra/.env.
# Warmup failure aborts the deploy (set -e) with the old stack still serving.
echo "» warming the model cache"
$COMPOSE run --rm -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 ml-warmup \
  || $COMPOSE run --rm ml-warmup

echo "» starting stack (http port ${HTTP_PORT})"
$COMPOSE up -d

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
