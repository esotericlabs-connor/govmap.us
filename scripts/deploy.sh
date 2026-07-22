#!/usr/bin/env bash
#
# GovMap production deploy — the single source of truth for shipping a change.
# Idempotent and re-runnable. Both manual deploys and the GitHub Actions
# self-hosted runner call this exact script (see .github/workflows/deploy.yml),
# so there's only one deploy path to reason about.
#
# Usage (on the VM):
#   bash scripts/deploy.sh             # full deploy: sync code, build, up, load data
#   bash scripts/deploy.sh --no-data   # code-only: skip the data pipeline step
#
# Safe to run as often as you like. It never touches .env (gitignored) or the
# Postgres volume.

set -euo pipefail

REPO_DIR="${GOVMAP_DIR:-/opt/govmap}"
BRANCH="main"
LOAD_DATA=1

for arg in "$@"; do
  case "$arg" in
    --no-data) LOAD_DATA=0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

cd "$REPO_DIR"

log "Syncing code to origin/$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
git --no-pager log --oneline -1

log "Ensuring .env exists"
if [ ! -f .env ]; then
  echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)" > .env
  chmod 600 .env
  echo "created .env with a generated POSTGRES_PASSWORD"
else
  echo ".env already present — leaving it untouched"
fi

log "Building and starting containers"
docker compose up -d --build

log "Waiting for the backend to become healthy"
# The backend applies Alembic migrations on start, so 'healthy' also means
# the schema is current. Poll /health rather than guessing with a fixed sleep.
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    healthy=1
    echo "backend healthy"
    break
  fi
  sleep 2
done
if [ "$healthy" -ne 1 ]; then
  echo "ERROR: backend did not become healthy in ~60s" >&2
  docker compose logs --tail=50 backend >&2
  exit 1
fi

if [ "$LOAD_DATA" -eq 1 ]; then
  log "Refreshing data (pipeline -> normalize)"
  # Non-fatal on purpose: a transient source outage (e.g. GitHub) shouldn't
  # fail the whole deploy — the app keeps serving whatever is already in the
  # DB. The weekly scheduler will retry regardless.
  if docker compose exec -T backend python -m app.pipelines.congress_legislators \
     && docker compose exec -T backend python -m app.normalize.members; then
    echo "data refresh complete"
  else
    echo "WARNING: data refresh failed — app is up on existing data; investigate" >&2
  fi
fi

log "Pruning superseded image layers"
docker image prune -f

log "Deploy complete"
docker compose ps

# Quick sanity signal: is the new backend code (deterministic photo_url) live?
if curl -fsS "http://localhost:8000/api/members?limit=1" 2>/dev/null | grep -q 'unitedstates.github.io'; then
  echo "verify: member photo_url is populated ✔"
else
  echo "verify: member photo_url not populated yet (empty DB, or --no-data was used)"
fi
