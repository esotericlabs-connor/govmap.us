#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository="$(cd -- "$script_dir/.." && pwd -P)"
source "$script_dir/backup-common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/restore-database.sh --backup FILE --identity-file FILE --confirm-isolated-empty-target

Restore an age-encrypted GovMap database dump to the local Compose database.
The backend must be stopped and the target must be a newly initialized, empty
database on an isolated recovery host. Existing databases are not replaced.
EOF
}

backup=""
identity=""
confirmed=0
while (($#)); do
  case "$1" in
    --backup)
      [[ $# -ge 2 && -n "$2" && -z "$backup" ]] || backup_die "Invalid --backup."
      backup="$2"
      shift 2
      ;;
    --identity-file)
      [[ $# -ge 2 && -n "$2" && -z "$identity" ]] || backup_die "Invalid --identity-file."
      identity="$2"
      shift 2
      ;;
    --confirm-isolated-empty-target)
      [[ "$confirmed" -eq 0 ]] || backup_die "Duplicate confirmation."
      confirmed=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      backup_die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$backup" && -n "$identity" && "$confirmed" -eq 1 ]] \
  || backup_die "The backup, identity, and empty-target confirmation are required."
[[ -f "$backup" && -r "$backup" ]] || backup_die "The backup file is not readable."
[[ -f "$identity" && -r "$identity" ]] || backup_die "The identity file is not readable."
backup_require_command age
backup_require_local_docker

backend="$(docker compose --file "$repository/docker-compose.yml" --project-directory "$repository" \
  ps --status running --quiet backend)" || backup_die "Could not check the backend status."
[[ -z "$backend" ]] || backup_die "Stop the backend before restoring a database."

if ! age --decrypt --identity "$identity" "$backup" > /dev/null; then
  backup_die "The backup could not be fully decrypted; no restore was attempted."
fi

check_sql="
SELECT
  (SELECT count(*) FROM pg_namespace
    WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'public')
      AND nspname !~ '^pg_')
  + (SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace)
  + (SELECT count(*) FROM pg_proc WHERE pronamespace = 'public'::regnamespace)
  + (SELECT count(*) FROM pg_type WHERE typnamespace = 'public'::regnamespace)
  + (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql')
  + (SELECT count(*) FROM pg_stat_activity
      WHERE datname = current_database() AND pid <> pg_backend_pid());
"
if ! objects="$(docker compose --file "$repository/docker-compose.yml" --project-directory "$repository" \
  exec -T postgres sh -c '
    set -eu
    : "${POSTGRES_USER:?POSTGRES_USER is required}"
    : "${POSTGRES_DB:?POSTGRES_DB is required}"
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    exec psql -X --no-password --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" \
      --no-align --tuples-only --set=ON_ERROR_STOP=1 --command="$1"
  ' -- "$check_sql")"; then
  backup_die "Could not verify that the target database is empty and idle."
fi
[[ "$objects" == "0" ]] \
  || backup_die "The target database is not empty or has other active connections."

if ! age --decrypt --identity "$identity" "$backup" \
  | docker compose --file "$repository/docker-compose.yml" --project-directory "$repository" \
    exec -T postgres sh -c '
      set -eu
      : "${POSTGRES_USER:?POSTGRES_USER is required}"
      : "${POSTGRES_DB:?POSTGRES_DB is required}"
      export PGPASSWORD="${POSTGRES_PASSWORD:-}"
      exec pg_restore --no-password --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" \
        --no-owner --no-acl --exit-on-error --single-transaction
    '; then
  backup_die "Restore failed. Keep the backend stopped and inspect the target before retrying."
fi

printf 'Database restore completed. Verify the migration revision and data before starting the backend.\n'
