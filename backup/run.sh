#!/usr/bin/env bash
set -Eeuo pipefail

# Entry point of the Compose "backup" service. It idles unless
# BACKUP_ENABLED=true; otherwise it runs govmap-backup once a day at
# BACKUP_TIME_UTC (HH:MM, default 02:30). On start it catches up only when the
# published bundle is missing or at least 24 hours old, so redeploys do not
# each create a backup. A failed run is logged and the schedule continues;
# the missing heartbeat raises the alert.

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

child=""
stop() {
  trap - TERM INT
  if [[ -n "$child" ]]; then
    kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
  fi
  log "Stopping."
  exit 143
}
trap stop TERM INT

# Sleep in the background so a stop signal is handled immediately.
pause() {
  sleep "$1" &
  child=$!
  wait "$child" || true
  child=""
}

if [[ "${BACKUP_ENABLED:-false}" != "true" ]]; then
  log "Backups are disabled (BACKUP_ENABLED is not \"true\"); idling."
  while true; do
    pause 86400
  done
fi

time_utc="${BACKUP_TIME_UTC:-02:30}"
if [[ ! "$time_utc" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  log "ERROR: BACKUP_TIME_UTC must be HH:MM in 24-hour UTC."
  exit 1
fi
bundle="${BACKUP_DIR:-/backups}/govmap-backup.tar.gz"

run_backup() {
  local status=0
  log "Starting backup."
  govmap-backup &
  child=$!
  wait "$child" || status=$?
  child=""
  if ((status == 0)); then
    log "Backup completed."
  else
    log "ERROR: Backup failed with exit status $status; the previous bundle was kept."
  fi
}

log "Backups enabled for target \"${BACKUP_TARGET:-}\"; daily at $time_utc UTC."

now="$(date -u +%s)"
mtime="$(stat -c %Y -- "$bundle" 2>/dev/null)" || mtime=0
if ((now - mtime >= 86400)); then
  log "The published bundle is missing or at least 24 hours old; running a catch-up backup."
  run_backup
fi

while true; do
  now="$(date -u +%s)"
  next="$(date -u -d "$(date -u +%F) $time_utc" +%s)"
  if ((next <= now)); then
    next=$((next + 86400))
  fi
  log "Next backup at $(date -u -d "@$next" '+%Y-%m-%dT%H:%M:%SZ')."
  pause $((next - now))
  run_backup
done
