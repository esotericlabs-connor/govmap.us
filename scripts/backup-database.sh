#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository="$(cd -- "$script_dir/.." && pwd -P)"
source "$script_dir/backup-common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/backup-database.sh --destination DIRECTORY --recipients-file FILE

Create a consistent PostgreSQL custom-format dump, encrypted with age.
The destination must exist outside the repository. No existing backup is removed.
EOF
}

destination=""
recipients=""
while (($#)); do
  case "$1" in
    --destination)
      [[ $# -ge 2 && -n "$2" && -z "$destination" ]] || backup_die "Invalid --destination."
      destination="$2"
      shift 2
      ;;
    --recipients-file)
      [[ $# -ge 2 && -n "$2" && -z "$recipients" ]] || backup_die "Invalid --recipients-file."
      recipients="$2"
      shift 2
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

[[ -n "$destination" && -n "$recipients" ]] || backup_die "Both arguments are required."
[[ -f "$recipients" && -r "$recipients" ]] || backup_die "The recipients file is not readable."
destination="$(backup_resolve_destination "$destination" "$repository")"
backup_require_command age
backup_require_local_docker

umask 077
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
temporary=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$temporary" && ( -e "$temporary" || -L "$temporary" ) ]]; then
    if ! rm -f -- "$temporary"; then
      printf 'ERROR: Could not remove the partial encrypted backup: %s\n' "$temporary" >&2
      status=1
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! temporary="$(mktemp "$destination/.govmap-db-${timestamp}-XXXXXXXXXX")"; then
  backup_die "Could not create a temporary encrypted backup."
fi

if ! docker compose --file "$repository/docker-compose.yml" --project-directory "$repository" \
  exec -T postgres sh -c '
    set -eu
    : "${POSTGRES_USER:?POSTGRES_USER is required}"
    : "${POSTGRES_DB:?POSTGRES_DB is required}"
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    exec pg_dump --no-password --format=custom --lock-wait-timeout=30s \
      --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
  ' | age --encrypt --recipients-file "$recipients" > "$temporary"; then
  backup_die "The database dump or encryption failed; no backup was published."
fi

name="${temporary##*/}"
output="$destination/${name#.}.dump.age"
backup_publish "$temporary" "$output"
temporary=""
printf '%s\n' "$output"
