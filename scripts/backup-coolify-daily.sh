#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: govmap-daily-backup [--resource-id ID] [--destination DIRECTORY] [--config-dir DIRECTORY]

Create one daily GovMap recovery bundle for a Coolify resource:
  DIRECTORY/govmap-backup.tar.gz

The bundle contains a consistent PostgreSQL custom-format dump (checked with
pg_restore --list), the backend log files, optionally a copy of the Coolify
deployment directory, a manifest, checksums and restore notes. The previous
bundle is replaced only after the new one is complete and verified; any failure
leaves it untouched. The bundle is NOT encrypted: keep the destination
root-only and encrypt the off-site copies (for example in Duplicati).

Options may also be supplied as environment variables (used by the systemd
unit): GOVMAP_RESOURCE_ID, GOVMAP_BACKUP_DIR, GOVMAP_CONFIG_DIR (optional).
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

resource_id="${GOVMAP_RESOURCE_ID:-}"
destination="${GOVMAP_BACKUP_DIR:-}"
config_dir="${GOVMAP_CONFIG_DIR:-}"
while (($#)); do
  case "$1" in
    --resource-id | --destination | --config-dir)
      [[ $# -ge 2 && -n "$2" ]] || die "Invalid $1."
      case "$1" in
        --resource-id) resource_id="$2" ;;
        --destination) destination="$2" ;;
        --config-dir) config_dir="$2" ;;
      esac
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "Unknown argument: $1"
      ;;
  esac
done

[[ "$resource_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{7,63}$ ]] \
  || die "A valid Coolify resource ID is required."
[[ -n "$destination" && -d "$destination" && ! -L "$destination" && -w "$destination" ]] \
  || die "The destination must be an existing writable directory (not a symlink)."
destination="$(cd -- "$destination" && pwd -P)" || die "Could not resolve the destination."
[[ -O "$destination" ]] || die "The destination must be owned by the user running the backup."
destination_mode="$(stat -c '%a' -- "$destination")" || die "Could not read destination permissions."
if ((8#$destination_mode & 8#077)); then
  die "The destination must not be accessible to group or others (use chmod 700)."
fi
if [[ -n "$config_dir" ]]; then
  [[ -d "$config_dir" && -r "$config_dir" ]] || die "The Coolify config directory is not readable."
fi

for command in docker flock tar gzip sha256sum stat mktemp; do
  require_command "$command"
done
if [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
  die "Unset DOCKER_HOST and DOCKER_CONTEXT and use the local Docker daemon."
fi
endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')" \
  || die "Could not inspect the current Docker context."
[[ "$endpoint" == unix://* ]] || die "The current Docker context is not a local Unix socket."
docker info >/dev/null 2>&1 || die "The local Docker daemon is unavailable."

running="$(docker ps --filter status=running --format '{{.Names}}')" \
  || die "Could not list running Docker containers."

# Coolify names containers <service>-<resource-id>-<YYYYMMDDTHHMMSS>.
find_container() {
  local prefix="$1-${resource_id}-" name found="" matches=0
  while IFS= read -r name; do
    [[ "$name" == "$prefix"* && "${name#"$prefix"}" =~ ^[0-9]{8}T[0-9]{6}$ ]] || continue
    found="$name"
    ((matches += 1))
  done <<< "$running"
  [[ "$matches" -eq 1 ]] \
    || die "Expected exactly one running $1 container for resource $resource_id; found $matches."
  printf '%s\n' "$found"
}
postgres_container="$(find_container postgres)"
backend_container="$(find_container backend)"

umask 077
exec 9>"$destination/.govmap-backup.lock"
flock -n 9 || die "A GovMap backup is already running."

output="$destination/govmap-backup.tar.gz"
[[ ! -d "$output" || -L "$output" ]] || die "$output is a directory; refusing to replace it."

workdir=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$workdir" && -d "$workdir" ]]; then
    rm -rf -- "$workdir" || {
      printf 'ERROR: Could not remove scratch directory %s\n' "$workdir" >&2
      status=1
    }
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

created="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
workdir="$(mktemp -d "$destination/.govmap-backup-work-XXXXXXXXXX")" \
  || die "Could not create a private scratch directory."
bundle="$workdir/govmap-backup"
mkdir -- "$bundle"

docker exec "$postgres_container" pg_isready --quiet --username=govmap --dbname=govmap \
  || die "PostgreSQL is not ready."
docker exec "$postgres_container" pg_dump \
  --no-password --format=custom --lock-wait-timeout=30s \
  --username=govmap --dbname=govmap > "$bundle/database.dump" \
  || die "pg_dump failed; the previous bundle was kept."
[[ -s "$bundle/database.dump" ]] || die "The database dump is empty."
docker exec -i "$postgres_container" pg_restore --list < "$bundle/database.dump" >/dev/null \
  || die "The database dump failed verification with pg_restore --list."
revision="$(docker exec "$postgres_container" psql --no-password --username=govmap \
  --dbname=govmap --no-align --tuples-only --command='SELECT version_num FROM alembic_version')" \
  || die "Could not read the Alembic revision."

docker cp "$backend_container:/app/logs" - > "$bundle/logs.tar" \
  || die "Could not copy backend logs."
[[ -s "$bundle/logs.tar" ]] || die "The log archive is empty."

config_status="not included"
if [[ -n "$config_dir" ]]; then
  cp -a -- "$config_dir" "$bundle/coolify-config" || die "Could not copy the Coolify config directory."
  config_status="included from $config_dir"
fi

postgres_image="$(docker inspect --format '{{.Config.Image}}' "$postgres_container")" \
  || die "Could not inspect the Postgres container."
{
  printf 'created_utc=%s\n' "$created"
  printf 'resource_id=%s\n' "$resource_id"
  printf 'postgres_container=%s\n' "$postgres_container"
  printf 'postgres_image=%s\n' "$postgres_image"
  printf 'backend_container=%s\n' "$backend_container"
  printf 'alembic_revision=%s\n' "$revision"
  printf 'coolify_config=%s\n' "$config_status"
} > "$bundle/MANIFEST.txt"

cat > "$bundle/RESTORE.txt" <<'EOF'
GovMap daily recovery bundle

  database.dump    PostgreSQL 16 custom-format dump of database "govmap"
  logs.tar         backend application and bug-report logs (/app/logs)
  coolify-config/  Coolify deployment files, including .env SECRETS (if present)
  MANIFEST.txt     creation time, containers, image and schema revision
  SHA256SUMS       verify with: sha256sum -c SHA256SUMS

Restore the database only into a NEW, EMPTY database on an isolated host,
never over a running production database:

  createdb govmap_restore
  pg_restore --no-owner --no-privileges --exit-on-error -d govmap_restore database.dump

coolify-config contains live credentials and the Cloudflare tunnel token.
Keep it private, and do not start the tunnel or scheduler from a copy while
production is running.
EOF

(cd -- "$bundle" && find . -type f ! -name SHA256SUMS -print0 | sort -z \
  | xargs -0 sha256sum --) > "$workdir/SHA256SUMS" || die "Could not compute checksums."
mv -- "$workdir/SHA256SUMS" "$bundle/SHA256SUMS"

tar -C "$workdir" -czf "$workdir/govmap-backup.tar.gz" govmap-backup \
  || die "Could not create the compressed bundle."
tar -tzf "$workdir/govmap-backup.tar.gz" >/dev/null \
  || die "The compressed bundle failed verification."
chmod 600 -- "$workdir/govmap-backup.tar.gz"

# Same-filesystem rename: readers see either the old bundle or the new one.
mv -fT -- "$workdir/govmap-backup.tar.gz" "$output" || die "Could not publish the bundle."
printf '%s\n' "$output"
