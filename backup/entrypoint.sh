#!/usr/bin/env bash
set -Eeuo pipefail

# The container starts as root only so it can take ownership of the host
# backup directory created on first deploy (root-owned when Docker creates
# it, or owned by the deployment platform's SSH user when it pre-creates it).
# It then drops to uid/gid 70 for the scheduler and every backup. Only a
# directory for a named, enabled target that is root-owned or empty is
# adopted; a non-empty directory owned by anyone else is left alone and the
# backup run fails instead.

uid=70
gid=70
destination="${BACKUP_DIR:-/backups}"
target="${BACKUP_TARGET:-}"

if [[ "$(id -u)" != "0" ]]; then
  exec govmap-backup-scheduler
fi

if [[ "${BACKUP_ENABLED:-false}" == "true" \
  && "$target" =~ ^[a-z0-9][a-z0-9-]{0,31}$ && "$target" != "unconfigured" \
  && -d "$destination" && ! -L "$destination" ]]; then
  owner="$(stat -c %u -- "$destination")"
  # An unreadable directory counts as non-empty, so it is never adopted.
  contents="$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" \
    || contents="unreadable"
  if [[ "$owner" != "$uid" && ( "$owner" == "0" || -z "$contents" ) ]]; then
    # Without CAP_FOWNER root can only chmod a directory it owns, so take
    # ownership first, restrict it, then hand it to the backup user.
    chown 0:0 -- "$destination"
    chmod 700 -- "$destination"
    chown "$uid:$gid" -- "$destination"
    printf 'Prepared %s for the backup user.\n' "$destination"
  fi
fi

exec setpriv --reuid="$uid" --regid="$gid" --clear-groups --inh-caps=-all -- govmap-backup-scheduler
