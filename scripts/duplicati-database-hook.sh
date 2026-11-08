#!/usr/bin/env bash

for argument in "$@"; do
  if [[ "$argument" == "--help" ]]; then
    printf 'ERROR: The Duplicati hook requires a database backup, not --help.\n' >&2
    exit 5
  fi
done

if ! script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"; then
  printf 'ERROR: Could not locate the database backup script.\n' >&2
  exit 5
fi

if bash "$script_dir/backup-database.sh" "$@"; then
  exit 0
else
  status=$?
  printf 'ERROR: Database backup failed (exit %s); abort the Duplicati backup.\n' "$status" >&2
  exit 5
fi
