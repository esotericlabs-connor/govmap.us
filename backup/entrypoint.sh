#!/usr/bin/env bash
set -Eeuo pipefail

# The container starts as root only so it can take ownership of the host
# backup directory that Docker auto-creates (root-owned) on first deploy. It
# then drops to uid/gid 70 for the scheduler and every backup. Only a
# root-owned directory for a named, enabled target is adopted; a directory
# owned by anyone else is left alone and the backup run fails instead.

uid=70
gid=70
destination="${BACKUP_DIR:-/backups}"
target="${BACKUP_TARGET:-}"

if [[ "$(id -u)" != "0" ]]; then
  exec govmap-backup-scheduler
fi

if [[ "${BACKUP_ENABLED:-false}" == "true" \
  && "$target" =~ ^[a-z0-9][a-z0-9-]{0,31}$ && "$target" != "unconfigured" \
  && -d "$destination" && ! -L "$destination" \
  && "$(stat -c %u -- "$destination")" == "0" ]]; then
  # chmod first, while root still owns the directory.
  chmod 700 -- "$destination"
  chown "$uid:$gid" -- "$destination"
  printf 'Prepared %s for the backup user.\n' "$destination"
fi

exec setpriv --reuid="$uid" --regid="$gid" --clear-groups --inh-caps=-all -- govmap-backup-scheduler
