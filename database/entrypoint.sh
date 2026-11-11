#!/usr/bin/env bash
set -Eeuo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

repository=/pgbackrest
uid=70
gid=70

[[ "${PGBACKREST_ENABLED:-false}" == "true" || "${PGBACKREST_ENABLED:-false}" == "false" ]] \
  || die "PGBACKREST_ENABLED must be true or false."
[[ -d "$repository" && ! -L "$repository" ]] \
  || die "The pgBackRest repository must be an existing directory (not a symlink)."

if [[ "$(id -u)" == "0" ]]; then
  owner="$(stat -c %u -- "$repository")" \
    || die "Could not read pgBackRest repository ownership."
  contents="$(find "$repository" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" \
    || die "Could not inspect the pgBackRest repository."
  if [[ "$owner" != "$uid" ]]; then
    [[ "$owner" == "0" || -z "$contents" ]] \
      || die "The non-empty pgBackRest repository is not owned by uid $uid."
    chown 0:0 -- "$repository"
    chmod 700 -- "$repository"
    chown "$uid:$gid" -- "$repository"
  else
    chmod 700 -- "$repository"
  fi
else
  [[ "$(id -u)" == "$uid" && -O "$repository" ]] \
    || die "The pgBackRest repository must be owned by uid $uid."
  chmod 700 -- "$repository" \
    || die "Could not restrict pgBackRest repository permissions."
fi

if [[ "${PGBACKREST_ENABLED:-false}" == "true" && "${1:-}" == "postgres" ]]; then
  set -- "$@" \
    -c archive_mode=on \
    -c 'archive_command=pgbackrest --stanza=govmap archive-push %p' \
    -c archive_timeout=300
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
