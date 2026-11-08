#!/usr/bin/env bash

backup_die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

backup_require_command() {
  command -v "$1" >/dev/null 2>&1 || backup_die "Required command not found: $1"
}

backup_require_local_docker() {
  backup_require_command docker
  if [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ]]; then
    backup_die "Unset DOCKER_HOST and DOCKER_CONTEXT and use a local Docker context."
  fi

  local endpoint
  if ! endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"; then
    backup_die "Could not inspect the current Docker context."
  fi
  case "$endpoint" in
    unix://*) ;;
    *) backup_die "The current Docker context is not a local Unix socket." ;;
  esac

  docker info >/dev/null 2>&1 || backup_die "The local Docker daemon is unavailable."
}

backup_resolve_destination() {
  local destination="$1"
  local repository="$2"
  [[ -d "$destination" && -w "$destination" ]] \
    || backup_die "The backup destination must be an existing writable directory."
  if ! destination="$(cd -- "$destination" && pwd -P)"; then
    backup_die "Could not resolve the backup destination."
  fi
  case "$destination/" in
    "$repository/"*) backup_die "The backup destination must be outside the repository." ;;
  esac
  printf '%s\n' "$destination"
}

backup_publish() {
  local temporary="$1"
  local destination="$2"
  [[ -f "$temporary" && ! -L "$temporary" && -s "$temporary" ]] \
    || backup_die "The encrypted output is missing, empty, or not a regular file."
  if ! ln --no-target-directory -- "$temporary" "$destination"; then
    backup_die "Could not publish the encrypted backup without replacing an existing path."
  fi
  if ! rm -- "$temporary"; then
    backup_die "The backup was published at $destination, but its temporary link could not be removed."
  fi
}
