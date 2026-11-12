#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: govmap-backup

Create one GovMap recovery bundle from inside the Compose "backup" service:
  $BACKUP_DIR/govmap-backup.tar.gz   (BACKUP_DIR defaults to /backups)

The bundle contains a consistent PostgreSQL custom-format dump (checked with
pg_restore --list), backend logs, non-secret deployment templates and backup
settings, a manifest, checksums and restore notes. Actual secrets and other
deployment overrides stay in the operator's vault. The previous bundle is
replaced only after the new one is complete and verified; any failure leaves
it untouched. The bundle is NOT
encrypted: keep the host directory private and encrypt off-site copies.

The destination fails closed. BACKUP_TARGET must name the environment (for
example "production"), and the destination must be owned by the backup user.
A misconfigured target or a destination not owned by the backup user fails
the run, and no heartbeat is sent.

Environment:
  BACKUP_TARGET         required environment name, [a-z0-9-], not "unconfigured"
  PGPASSWORD            required database password
  PGHOST/PGPORT/PGUSER/PGDATABASE   default postgres/5432/govmap/govmap
  BACKUP_DIR            default /backups
  BACKUP_LOG_DIR        default /logs (read-only mount of the backend logs)
  BACKUP_CONFIG_DIR     default /usr/local/share/govmap-recovery (baked-in
                        non-secret recovery files; normally leave unchanged)
  BACKUP_HEARTBEAT_URL  optional https URL requested after each published
                        bundle; passed to curl on stdin, never on the
                        command line
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

case "${1:-}" in
  "") ;;
  --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    die "Unknown argument: $1"
    ;;
esac

target="${BACKUP_TARGET:-}"
destination="${BACKUP_DIR:-/backups}"
log_dir="${BACKUP_LOG_DIR:-/logs}"
config_dir="${BACKUP_CONFIG_DIR:-/usr/local/share/govmap-recovery}"
heartbeat_url="${BACKUP_HEARTBEAT_URL:-}"
export PGHOST="${PGHOST:-postgres}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-govmap}"
export PGDATABASE="${PGDATABASE:-govmap}"

[[ "$target" =~ ^[a-z0-9][a-z0-9-]{0,31}$ && "$target" != "unconfigured" ]] \
  || die "BACKUP_TARGET must name this environment (lowercase letters, digits and hyphens)."
[[ -n "${PGPASSWORD:-}" ]] || die "PGPASSWORD is required."
[[ -d "$destination" && ! -L "$destination" && -w "$destination" ]] \
  || die "The destination $destination must be an existing writable directory (not a symlink)."
destination="$(cd -- "$destination" && pwd -P)" || die "Could not resolve the destination."
[[ -O "$destination" ]] || die "The destination must be owned by the user running the backup."
destination_mode="$(stat -c '%a' -- "$destination")" || die "Could not read destination permissions."
if ((8#$destination_mode & 8#077)); then
  chmod 700 -- "$destination" || die "Could not restrict the destination to its owner."
fi
[[ -d "$log_dir" && -r "$log_dir" && -x "$log_dir" ]] || die "The log directory $log_dir is not readable."

config_files=(docker-compose.PaaS.yml pgbackrest.conf database.Dockerfile backup.Dockerfile backup-service.md source-commit.txt)
[[ -d "$config_dir" && ! -L "$config_dir" ]] || die "The recovery configuration directory must be a real directory."
for file in "${config_files[@]}"; do
  [[ -f "$config_dir/$file" && ! -L "$config_dir/$file" && -s "$config_dir/$file" && -r "$config_dir/$file" ]] \
    || die "Required recovery configuration file is missing, empty, unreadable or a symlink: $file"
done
source_commit="$(< "$config_dir/source-commit.txt")"
[[ "$source_commit" =~ ^(unknown|[a-f0-9]{40})$ ]] || die "Invalid recovery configuration source commit."
if [[ "$source_commit" == "unknown" ]]; then
  printf 'WARNING: Backup image source commit is unknown; configuration provenance is not verified.\n' >&2
fi

logical_enabled="${BACKUP_ENABLED:-false}"
logical_time="${BACKUP_TIME_UTC:-02:30}"
logical_interval="${BACKUP_INTERVAL_MINUTES:-1440}"
pitr_enabled="${GOVMAP_PGBACKREST_ENABLED:-false}"
pitr_time="${GOVMAP_PGBACKREST_TIME_UTC:-03:30}"
[[ "$logical_enabled" =~ ^(true|false)$ && "$pitr_enabled" =~ ^(true|false)$ ]] \
  || die "Backup enablement settings must be true or false."
[[ "$logical_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ && "$pitr_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] \
  || die "Backup schedule times must be HH:MM in 24-hour UTC."
if [[ ! "$logical_interval" =~ ^[1-9][0-9]{0,3}$ ]] \
  || ((logical_interval < 5 || logical_interval > 1440 || 1440 % logical_interval != 0)); then
  die "BACKUP_INTERVAL_MINUTES must be 5-1440 and divide 1440 evenly."
fi

if [[ -n "$heartbeat_url" ]]; then
  heartbeat_pattern='^https://[^[:space:]"\]+$'
  [[ "$heartbeat_url" =~ $heartbeat_pattern ]] \
    || die "BACKUP_HEARTBEAT_URL must be a single https:// URL."
  require_command curl
fi

for command in pg_isready pg_dump pg_restore psql flock tar gzip sha256sum stat mktemp cp; do
  require_command "$command"
done

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
mkdir -- "$bundle/deployment-config"
for file in "${config_files[@]}"; do
  cp -- "$config_dir/$file" "$bundle/deployment-config/$file" \
    || die "Could not copy required recovery configuration: $file"
done
{
  printf 'BACKUP_TARGET=%s\n' "$target"
  printf 'BACKUP_ENABLED=%s\n' "$logical_enabled"
  printf 'BACKUP_TIME_UTC=%s\n' "$logical_time"
  printf 'BACKUP_INTERVAL_MINUTES=%s\n' "$logical_interval"
  printf 'GOVMAP_PGBACKREST_ENABLED=%s\n' "$pitr_enabled"
  printf 'GOVMAP_PGBACKREST_TIME_UTC=%s\n' "$pitr_time"
} > "$bundle/deployment-config/backup-settings.env"

pg_isready --quiet --timeout=30 || die "PostgreSQL is not ready."
pg_dump --no-password --format=custom --lock-wait-timeout=30s > "$bundle/database.dump" \
  || die "pg_dump failed; the previous bundle was kept."
[[ -s "$bundle/database.dump" ]] || die "The database dump is empty."
pg_restore --list "$bundle/database.dump" >/dev/null \
  || die "The database dump failed verification with pg_restore --list."
revision="$(psql --no-password --no-align --tuples-only \
  --command='SELECT version_num FROM alembic_version')" \
  || die "Could not read the Alembic revision."
server_version="$(psql --no-password --no-align --tuples-only --command='SHOW server_version')" \
  || die "Could not read the PostgreSQL server version."
dump_version="$(pg_dump --version)" || die "Could not read the pg_dump version."

# Unreadable log files produce tar warnings and are skipped rather than
# failing the database backup.
tar --ignore-failed-read -C "$log_dir" -cf "$bundle/logs.tar" . \
  || die "Could not archive the backend logs."
[[ -s "$bundle/logs.tar" ]] || die "The log archive is empty."

{
  printf 'created_utc=%s\n' "$created"
  printf 'backup_target=%s\n' "$target"
  printf 'postgres_server_version=%s\n' "$server_version"
  printf 'pg_dump_version=%s\n' "$dump_version"
  printf 'alembic_revision=%s\n' "$revision"
  printf 'deployment_config=%s\n' "included (non-secret templates and backup settings only)"
  printf 'deployment_config_version=1\n'
  printf 'source_commit=%s\n' "$source_commit"
  printf 'secrets=%s\n' "not included (kept in the operator's vault)"
} > "$bundle/MANIFEST.txt"

cat > "$bundle/RESTORE.txt" <<'EOF'
GovMap recovery bundle (container backup service)

  database.dump  PostgreSQL 16 custom-format dump of database "govmap"
  logs.tar       backend application and bug-report logs (/app/logs)
  MANIFEST.txt   creation time, environment, versions and schema revision
  SHA256SUMS     verify with: sha256sum -c SHA256SUMS
  deployment-config/  non-secret templates, backup settings and recovery guide

deployment-config/source-commit.txt identifies the backup image's source.
The Compose template is unrendered, not an export of the running deployment.
backup-settings.env records only the backup service's switches and schedules.
Recover the matching application source and any other deployment overrides
from Git and the operator's vault; do not assume template defaults were used.

Secrets are not included: POSTGRES_PASSWORD, CLOUDFLARE_TUNNEL_TOKEN, source
API credentials, INTERNAL_USER/INTERNAL_PASSWORD, TURNSTILE_SECRET_KEY,
ALERT_WEBHOOK_URL and the three backup heartbeat URLs must come from the vault.
The external backup encryption passphrase must be recoverable separately too.

Restore the database only into a NEW, EMPTY database on an isolated host,
never over a running production database:

  createdb govmap_restore
  pg_restore --no-owner --no-privileges --exit-on-error -d govmap_restore database.dump

For isolated Docker recovery, PITR, verification and cutover, follow
deployment-config/backup-service.md. Keep ingestion and upstream-dependent
traffic disabled until the documented request-budget recovery rules are met.
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

# The bundle is already published, so a failed ping only warns; the monitor
# raises the alert when the ping does not arrive.
if [[ -n "$heartbeat_url" ]]; then
  if ! printf 'url = "%s"\n' "$heartbeat_url" \
    | curl --config - --fail --silent --show-error --max-time 10 --retry 3 --output /dev/null; then
    printf 'WARNING: The bundle was published, but the heartbeat ping failed.\n' >&2
  fi
fi
