#!/usr/bin/env bash
set -Eeuo pipefail

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

pause() {
  sleep "$1" &
  child=$!
  wait "$child" || true
  child=""
}

if [[ "${PGBACKREST_ENABLED:-false}" != "true" ]]; then
  log "pgBackRest is disabled (PGBACKREST_ENABLED is not \"true\"); idling."
  while true; do
    pause 86400
  done
fi

time_utc="${PGBACKREST_TIME_UTC:-03:30}"
if [[ ! "$time_utc" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  log "ERROR: PGBACKREST_TIME_UTC must be HH:MM in 24-hour UTC."
  exit 1
fi

heartbeat_archive="${PGBACKREST_ARCHIVE_HEARTBEAT_URL:-}"
heartbeat_backup="${PGBACKREST_BACKUP_HEARTBEAT_URL:-}"
heartbeat_pattern='^https://[^[:space:]"\\]+$'
for value in "$heartbeat_archive" "$heartbeat_backup"; do
  if [[ -n "$value" && ! "$value" =~ $heartbeat_pattern ]]; then
    log "ERROR: pgBackRest heartbeat URLs must be single https:// URLs."
    exit 1
  fi
done

ping_heartbeat() {
  local url="$1"
  local label="$2"
  [[ -n "$url" ]] || return 0
  if printf 'url = "%s"\n' "$url" \
    | curl --config - --fail --silent --show-error --max-time 10 --retry 3 --output /dev/null; then
    log "$label heartbeat sent."
  else
    log "WARNING: $label completed, but its heartbeat ping failed."
  fi
}

run_check() {
  log "Checking stanza and archived WAL."
  if pgbackrest --stanza=govmap check; then
    log "pgBackRest archive check completed."
    ping_heartbeat "$heartbeat_archive" "Archive check"
    return 0
  fi
  log "ERROR: pgBackRest archive check failed; no archive heartbeat sent."
  return 1
}

latest_full_timestamp() {
  pgbackrest --stanza=govmap info --output=json \
    | jq -er '[.[].db[]?.backup[]? | select(.type == "full") | .timestamp.stop] | max // 0'
}

run_full_backup() {
  log "Starting pgBackRest full backup."
  if pgbackrest --stanza=govmap --type=full backup; then
    log "pgBackRest full backup completed."
    ping_heartbeat "$heartbeat_backup" "Full backup"
    return 0
  fi
  log "ERROR: pgBackRest full backup failed; no full-backup heartbeat sent."
  return 1
}

log "pgBackRest enabled for target \"${BACKUP_TARGET:-}\"; full backup daily at $time_utc UTC; archive checks every 15 minutes."

if ! run_check; then
  log "The scheduler will retry the archive check in 15 minutes."
fi

last_full="$(latest_full_timestamp)" \
  || {
    log "ERROR: Could not read pgBackRest backup history; verify stanza creation and repository access."
    exit 1
  }
[[ "$last_full" =~ ^[0-9]+$ ]] \
  || {
    log "ERROR: pgBackRest returned an invalid full-backup timestamp."
    exit 1
  }
now="$(date -u +%s)"
retry_full=0
if ((last_full == 0 || now - last_full >= 86400)); then
  log "No full backup exists or the latest is at least 24 hours old; running a catch-up backup."
  if ! run_full_backup; then
    log "Retrying the full backup in 15 minutes."
    retry_full=$(( $(date -u +%s) + 900 ))
  fi
fi

now="$(date -u +%s)"
anchor="$(date -u -d "$(date -u +%F) $time_utc" +%s)"
next_full="$anchor"
if ((next_full <= now)); then
  next_full=$((next_full + 86400))
fi
next_check=$((now + 900))

while true; do
  now="$(date -u +%s)"
  wait_seconds=$((next_check - now))
  if ((next_full - now < wait_seconds)); then
    wait_seconds=$((next_full - now))
  fi
  if ((retry_full > 0 && retry_full - now < wait_seconds)); then
    wait_seconds=$((retry_full - now))
  fi
  ((wait_seconds > 0)) || wait_seconds=1
  log "Next archive check within $wait_seconds seconds; next full backup at $(date -u -d "@$next_full" '+%Y-%m-%dT%H:%M:%SZ')."
  pause "$wait_seconds"

  now="$(date -u +%s)"
  if ((now >= next_full)); then
    if run_full_backup; then
      retry_full=0
    else
      log "Retrying the full backup in 15 minutes."
      retry_full=$(( $(date -u +%s) + 900 ))
    fi
    next_full=$((next_full + 86400))
  elif ((retry_full > 0 && now >= retry_full)); then
    if run_full_backup; then
      retry_full=0
    else
      log "Retrying the full backup in 15 minutes."
      retry_full=$(( $(date -u +%s) + 900 ))
    fi
  fi
  if ((now >= next_check)); then
    run_check || true
    next_check=$((now + 900))
  fi
done
