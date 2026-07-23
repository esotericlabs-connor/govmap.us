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

check_prereqs() {
  log "Checking prerequisites"
  local missing=0

  for cmd in git curl openssl docker; do
    if command -v "$cmd" >/dev/null 2>&1; then
      echo "  ✔ $cmd"
    else
      echo "  ✗ $cmd — MISSING"
      missing=1
    fi
  done

  # docker compose is a plugin subcommand, not its own binary.
  if docker compose version >/dev/null 2>&1; then
    echo "  ✔ docker compose"
  else
    echo "  ✗ docker compose — MISSING (need the Compose v2 plugin)"
    missing=1
  fi

  # Catches a running-but-unreachable daemon, usually "not in the docker group".
  if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
    echo "  ✗ docker daemon not reachable as $(whoami) — daemon down, or you're not in the 'docker' group"
    missing=1
  fi

  if [ "$missing" -ne 0 ]; then
    cat >&2 <<'EOF'

  ── Missing prerequisites. On Ubuntu, install them, then re-run this script ──

  # base tools
  sudo apt-get update && sudo apt-get install -y ca-certificates curl git openssl

  # Docker Engine + Compose plugin (official repo)
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # run docker without sudo, then LOG OUT AND BACK IN for it to take effect
  sudo usermod -aG docker "$USER"

  Then: bash scripts/deploy.sh
EOF
    exit 1
  fi
  echo "  all prerequisites present"
}

check_prereqs

cd "$REPO_DIR"

log "Syncing code to origin/$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
git --no-pager log --oneline -1

log "Ensuring .env exists"
if [ ! -f .env ]; then
  {
    echo "# GovMap production secrets. Back this file up — restoring it makes a"
    echo "# rebuild instant. See .env.example for the full reference."
    echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
    echo "# Cloudflare Tunnel token — required for the public site to come up."
    echo "# Fetch from the CF dashboard (govmap tunnel -> connector -> --token)."
    echo "CLOUDFLARE_TUNNEL_TOKEN="
  } > .env
  chmod 600 .env
  echo "created a fresh .env with a generated POSTGRES_PASSWORD"
  echo "ACTION NEEDED: set CLOUDFLARE_TUNNEL_TOKEN in .env to bring the public site up"
else
  echo ".env already present — leaving it untouched"
fi

log "Building and starting containers"
# Enable the cloudflared tunnel service only when a token is configured, so the
# same compose file works for local dev (no tunnel) and production (tunnel up).
if grep -Eq '^CLOUDFLARE_TUNNEL_TOKEN=.+' .env 2>/dev/null; then
  export COMPOSE_PROFILES=tunnel
  echo "cloudflared tunnel: ENABLED (token found in .env)"
else
  echo "cloudflared tunnel: disabled (set CLOUDFLARE_TUNNEL_TOKEN in .env to enable)"
fi
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
  # DB. The scheduler retries regardless. `refresh` pulls + normalizes every
  # registered source and records each outcome to the pipeline_status table.
  if docker compose exec -T backend python -m app.pipelines.refresh; then
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
