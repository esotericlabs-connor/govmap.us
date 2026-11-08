#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository="$(cd -- "$script_dir/.." && pwd -P)"
source "$script_dir/backup-common.sh"

usage() {
  cat <<'EOF'
Usage: bash scripts/backup-govmap.sh --destination DIRECTORY --recipients-file FILE

Create one age-encrypted archive containing the GovMap repository and .env,
a consistent encrypted PostgreSQL dump, and encrypted persistent logs.
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
[[ -f "$repository/.env" && -r "$repository/.env" && ! -L "$repository/.env" ]] \
  || backup_die "The repository .env must be a readable regular file, not a symlink."
destination="$(backup_resolve_destination "$destination" "$repository")"
backup_require_command age
backup_require_command tar
backup_require_local_docker

backend_id="$(docker compose --file "$repository/docker-compose.yml" --project-directory "$repository" \
  ps --all --quiet backend)" || backup_die "Could not identify the backend container."
[[ "$backend_id" =~ ^[0-9a-f]{12,64}$ ]] || backup_die "The backend container is unavailable."
logs_volume="$(docker inspect --format \
  '{{range .Mounts}}{{if and (eq .Destination "/app/logs") (eq .Type "volume")}}{{.Name}}{{end}}{{end}}' \
  "$backend_id")" || backup_die "Could not inspect the backend log volume."
[[ "$logs_volume" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] \
  || backup_die "The persistent log volume is unavailable."
docker image inspect postgres:16-alpine >/dev/null 2>&1 \
  || backup_die "The local postgres:16-alpine image is required to read the log volume."

umask 077
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
workdir=""
database_dump=""
output=""
published=0
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$workdir" && -d "$workdir" ]]; then
    if [[ -n "$database_dump" && "$database_dump" == "$workdir/"* ]]; then
      if ! rm -f -- "$database_dump"; then
        printf 'ERROR: Could not remove an intermediate database dump.\n' >&2
        status=1
      fi
    fi
    if ! rm -f -- "$workdir/recipients" "$workdir/database.dump.age" \
      "$workdir/logs.tar.age" "$workdir/archive.partial"; then
      printf 'ERROR: Could not remove intermediate files in %s\n' "$workdir" >&2
      status=1
    fi
    if ! rmdir -- "$workdir"; then
      printf 'ERROR: Backup scratch directory requires inspection: %s\n' "$workdir" >&2
      status=1
    fi
  fi
  if [[ "$status" -eq 0 && "$published" -eq 1 ]]; then
    printf '%s\n' "$output"
  elif [[ "$published" -eq 1 ]]; then
    printf 'ERROR: An encrypted archive was created, but cleanup failed: %s\n' "$output" >&2
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! workdir="$(mktemp -d "$destination/.govmap-${timestamp}-XXXXXXXXXX")"; then
  backup_die "Could not create the backup scratch directory."
fi
if ! cp -- "$recipients" "$workdir/recipients"; then
  backup_die "Could not snapshot the recipients file."
fi
recipients="$workdir/recipients"

if ! database_dump="$(bash "$script_dir/backup-database.sh" \
  --destination "$workdir" --recipients-file "$recipients")"; then
  backup_die "The database backup failed."
fi
case "$database_dump" in
  "$workdir/"*.dump.age) ;;
  *) backup_die "The database backup returned an unexpected path." ;;
esac
mv -- "$database_dump" "$workdir/database.dump.age" \
  || backup_die "Could not stage the encrypted database dump."
database_dump=""

if ! docker run --rm --pull=never --network none \
  --mount "type=volume,source=$logs_volume,destination=/source,readonly" \
  --entrypoint tar postgres:16-alpine -C /source -cf - . \
  | age --encrypt --recipients-file "$recipients" > "$workdir/logs.tar.age"; then
  backup_die "The persistent log backup or encryption failed."
fi
[[ -s "$workdir/logs.tar.age" ]] || backup_die "The encrypted log backup is empty."

if ! tar --create --file=- --hard-dereference \
  --exclude='./.venv' \
  --exclude='./backend/.venv' \
  --exclude='./backend/data/staging' \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/.next' \
  --exclude='*/__pycache__' \
  --transform='s,^\.,app,SH' \
  --directory="$repository" . \
  --directory="$workdir" database.dump.age logs.tar.age \
  | age --encrypt --recipients-file "$recipients" > "$workdir/archive.partial"; then
  backup_die "The application archive or encryption failed; no backup was published."
fi

name="${workdir##*/}"
output="$destination/${name#.}.tar.age"
backup_publish "$workdir/archive.partial" "$output"
published=1
