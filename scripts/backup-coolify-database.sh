#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository="$(cd -- "$script_dir/.." && pwd -P)"
source "$script_dir/backup-common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/backup-coolify-database.sh \
  --resource-id ID --destination DIRECTORY --recipients-file FILE

Create a consistent PostgreSQL custom-format dump from exactly one running
Coolify Postgres container, encrypt it with age, and publish it atomically.
The destination must exist outside the repository. No existing backup is removed.
EOF
}

resource_id=""
destination=""
recipients=""
while (($#)); do
  case "$1" in
    --resource-id)
      [[ $# -ge 2 && -n "$2" && -z "$resource_id" ]] \
        || backup_die "Invalid --resource-id."
      resource_id="$2"
      shift 2
      ;;
    --destination)
      [[ $# -ge 2 && -n "$2" && -z "$destination" ]] \
        || backup_die "Invalid --destination."
      destination="$2"
      shift 2
      ;;
    --recipients-file)
      [[ $# -ge 2 && -n "$2" && -z "$recipients" ]] \
        || backup_die "Invalid --recipients-file."
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

[[ "$resource_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{7,63}$ ]] \
  || backup_die "A valid Coolify resource ID is required."
[[ -n "$destination" && -n "$recipients" ]] \
  || backup_die "The destination and recipients file are required."
[[ -f "$recipients" && -r "$recipients" ]] \
  || backup_die "The recipients file is not readable."
destination="$(backup_resolve_destination "$destination" "$repository")"
backup_require_command age
backup_require_command flock
backup_require_local_docker

container_names="$(docker ps --filter status=running --format '{{.Names}}')" \
  || backup_die "Could not list running Docker containers."
prefix="postgres-${resource_id}-"
postgres_container=""
matches=0
while IFS= read -r name; do
  [[ "$name" == "$prefix"* ]] || continue
  suffix="${name#"$prefix"}"
  [[ "$suffix" =~ ^[0-9]{8}T[0-9]{6}$ ]] || continue
  postgres_container="$name"
  ((matches += 1))
done <<< "$container_names"
[[ "$matches" -eq 1 ]] \
  || backup_die "Expected exactly one running Postgres container for resource $resource_id; found $matches."

umask 077
exec 9>"$destination/.govmap-db-${resource_id}.lock"
flock -n 9 || backup_die "A database backup for resource $resource_id is already running."

if ! docker exec "$postgres_container" pg_isready \
  --quiet --username=govmap --dbname=govmap; then
  backup_die "The selected Postgres container is not ready."
fi

timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
workdir=""
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
  if [[ -n "$workdir" && -d "$workdir" ]]; then
    if ! rmdir -- "$workdir"; then
      printf 'ERROR: Backup scratch directory requires inspection: %s\n' "$workdir" >&2
      status=1
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

workdir="$(mktemp -d "$destination/.govmap-db-work-${timestamp}-XXXXXXXXXX")" \
  || backup_die "Could not create a private scratch directory."
temporary="$(mktemp "$workdir/dump-XXXXXXXXXXXX")" \
  || backup_die "Could not create a private temporary backup."

if ! docker exec "$postgres_container" pg_dump \
  --no-password --format=custom --lock-wait-timeout=30s \
  --username=govmap --dbname=govmap \
  | age --encrypt --recipients-file "$recipients" > "$temporary"; then
  backup_die "The database dump or encryption failed; no backup was published."
fi

[[ -s "$temporary" ]] || backup_die "The encrypted database backup is empty."
random_suffix="${temporary##*/dump-}"
output="$destination/govmap-${resource_id}-${timestamp}-${random_suffix}.dump.age"
backup_publish "$temporary" "$output"
temporary=""
if ! rmdir -- "$workdir"; then
  backup_die "The encrypted backup was published, but its scratch directory could not be removed."
fi
workdir=""
printf '%s\n' "$output"
