# GovMap backup service

This guide describes the repository's backup service without identifying a
particular host or deployment provider. It is intended for an operator who
needs to create, monitor and rehearse recovery of a GovMap backup.

**Protect the backups:** Neither local backup directory is encrypted. The
logical bundle contains database contents and private logs; the pgBackRest
repository contains the database cluster and its WAL. Keep both directories
and any restored copies private. Duplicati encrypts off-site copies. Do not
put credentials, passphrases, monitor URLs, private hostnames or actual
resource identifiers in the repository, screenshots or support messages.

## What it does

Two backup services run in the same Compose stack:

1. `pgbackrest` continuously archives WAL from PostgreSQL, checks the archive
   every 15 minutes, and creates a full cluster backup daily at
   `PGBACKREST_TIME_UTC` (default `03:30` UTC). pgBackRest expires backups
   using a seven-day time-based full-backup retention policy. Its repository
   is local to this resource, under `./pgbackrest`.
2. `backup` creates a separate logical `pg_dump` bundle and logs daily at
   `BACKUP_TIME_UTC` (default `02:30` UTC) under `./backups`. It is an
   independent fallback, not the source of PITR.

The pgBackRest sidecar shares only the private repository, a read-only mount
of PostgreSQL data files, and a private local socket. PostgreSQL sends WAL to
the same repository from its own container. Neither service needs a published
database port, Docker socket or host script. Duplicati copies the two folders
off-site; it remains the only off-site backup product.

The logical bundle is assembled in a private scratch directory and atomically
replaces its previous copy only after verification. The scheduler and
pgBackRest sidecar run as uid/gid `70` without capabilities on a read-only
root filesystem. PostgreSQL uses a custom image based on the existing
digest-pinned PostgreSQL 16 Alpine image, with pgBackRest added.

The database image gets pgBackRest from Alpine 3.24 (currently 2.58) and the
sidecar gets it from Alpine 3.22 (currently 2.55). The two exchange only
repository files and never use pgBackRest's remote protocol, where matching
versions are required, and the 2.56 to 2.58 release notes list no
repository-format change. Dev acceptance and the restore rehearsal below are
the proof (stanza, archive check, full backup and restore); after them, move
the sidecar to a newer Alpine so both match.

**Deployment configuration and secrets are not included.** The `.env` values,
tunnel token and other credentials are kept in the operator's vault and must
be recoverable independently of the server.

The worker's `worker-staging` volume is not included either: it holds only the
latest source snapshots, which the next refresh of each source rewrites.

The database dump includes `upstream_budgets` and `upstream_requests` (0015).
A restored ledger cannot include requests made after the backup. Before
reusing the same source credentials on a restored environment, stop all old
callers and allow a full 60-minute drain with upstream-dependent traffic and
refreshes disabled. Do not clear the ledger or run old and restored instances
against the same keys. Isolated dev/restore exercises need separate keys.

### Destination

`./backups` and `./pgbackrest` are separate directories inside **that
resource's own directory** on the host. Relative paths give dev and
production separate data directories automatically. No host setup is needed:
the PostgreSQL entrypoint prepares the pgBackRest directory as mode `700`,
owner `70:70`, adopting only a root-owned or empty directory. The logical
backup entrypoint prepares `./backups` when logical backups are enabled.
A non-empty directory owned by another user is never adopted.

A logical backup refuses to start, and sends no heartbeat, unless
`BACKUP_TARGET` names the environment (lowercase letters, digits and hyphens,
up to 32 characters, not `unconfigured`) and its directory is a real
directory owned by uid `70`. Group or other access is removed automatically.
Keep off-site copies: deleting and recreating a resource can delete both
local directories.

Find the host path from the running container (see
[Monitor and run a backup](#monitor-and-run-a-backup)):

```bash
sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/backups"}}{{.Source}}{{end}}{{end}}' "$BACKUP_CONTAINER"
```

For pgBackRest, replace `/backups` with `/pgbackrest` and use the pgBackRest
container name. The resource's directory also holds deployment settings,
including secrets. Select only `backups` and `pgbackrest` in Duplicati, never
the resource directory or its parent.

### Schedule

The backup service runs a daily logical dump. PostgreSQL archives WAL
continuously when pgBackRest is enabled; its sidecar checks the archive every
15 minutes and runs the daily full backup:

- `BACKUP_ENABLED` other than `true` (the default): it logs that backups are
  disabled and idles. Use this for test environments.
- `BACKUP_ENABLED=true`: it runs daily at `BACKUP_TIME_UTC` (`02:30` UTC by
  default). The bundle is created immediately on startup only if missing or
  at least 24 hours old.
- `PGBACKREST_ENABLED=false` (the default): PostgreSQL archiving stays off and
  the pgBackRest scheduler idles. Do not turn it on until the stanza has been
  created; see [Bootstrap pgBackRest](#bootstrap-pgbackrest).
- `PGBACKREST_ENABLED=true`: PostgreSQL archives WAL with a 5-minute
  `archive_timeout`. The sidecar runs `pgbackrest check` every 15 minutes and
  a full backup daily at `PGBACKREST_TIME_UTC` (`03:30` UTC by default). It
  catches up at startup if no full backup exists or the last one is at least
  24 hours old. Failed archive checks are logged and retried after 15 minutes.
  Failed full backups are logged and retried every 15 minutes until one
  succeeds; neither failure sends its corresponding heartbeat.
- Stopping or redeploying the container interrupts a run in progress; the
  previous bundle is kept and the scratch directory is removed.
- Asynchronous archiving enables the `archive-push-queue-max=4GiB` safeguard.
  Push runs are bounded to 1 GiB so the queue limit is rechecked regularly.
  If the queue exceeds the limit, pgBackRest discards queued WAL rather than
  allowing `pg_wal` to fill and stop PostgreSQL. That creates a PITR gap; a
  new successful full backup is required to restore complete recovery
  coverage. Monitor PostgreSQL logs, archive-check heartbeats, repository
  free space and Duplicati job reports.

Run only one enabled backup stack per environment.

### Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKUP_ENABLED` | `false` | `true` turns on the daily logical dump |
| `BACKUP_TARGET` | `unconfigured` | Environment name; recorded in the manifest and required before any run |
| `BACKUP_INTERVAL_MINUTES` | `1440` | Logical dump interval; 1440 is once daily |
| `BACKUP_TIME_UTC` | `02:30` | Daily logical dump time in UTC |
| `BACKUP_HEARTBEAT_URL` | empty | Private `https` dead-man's-switch URL; store it as a secret |
| `PGBACKREST_ENABLED` | `false` | Enables PostgreSQL WAL archiving and pgBackRest schedules; stanza must already exist |
| `PGBACKREST_TIME_UTC` | `03:30` | Daily full backup time in UTC |
| `PGBACKREST_ARCHIVE_HEARTBEAT_URL` | empty | Optional `https` heartbeat after each successful 15-minute archive check |
| `PGBACKREST_BACKUP_HEARTBEAT_URL` | empty | Optional `https` heartbeat after each successful full backup |

The heartbeat URL is passed to `curl` on stdin so its token never appears in
the process list. The database password comes from `POSTGRES_PASSWORD`.

### Bundle contents

The logical backup is `backups/govmap-backup.tar.gz`. The pgBackRest
repository is a directory tree under `pgbackrest/` containing full backups,
metadata and WAL archives. Neither heartbeat proves that an off-site copy
exists or can be restored. Duplicati copies both trees; exclude
`.govmap-backup-work-*` and `.govmap-backup.lock` from its selection.

| Item | Purpose |
| --- | --- |
| `database.dump` | Consistent custom-format dump of the `govmap` PostgreSQL database |
| `logs.tar` | The shared `/app/logs` volume: API (`app.log`), refresh worker (`worker.log`) and bug-report logs |
| `MANIFEST.txt` | Creation time, backup target, PostgreSQL server and `pg_dump` versions, Alembic revision |
| `SHA256SUMS` | Checksums of the recorded files |
| `RESTORE.txt` | Basic restore notes for that bundle |

Bundles from the earlier host-timer script also contain a deployment
configuration directory and a different manifest layout. Use each bundle's
own manifest and restore notes.

The database dump and logs are collected separately, so they are not a single
transactionally synchronized snapshot. The bundle does not recreate the
operating system, deployment platform, off-site backup configuration,
external routes or policies, PostgreSQL cluster-wide roles, or the deployed
source commit. Record the deployed commit and keep recovery credentials
independently of the server.

## Bootstrap pgBackRest

Do this in dev first on a reviewed, CI-green revision. Keep
`PGBACKREST_ENABLED=false` during the initial deployment so PostgreSQL starts
without archiving while the repository is initialized.

1. Deploy the new PostgreSQL image and Compose services with
   `PGBACKREST_ENABLED=false`. Confirm PostgreSQL becomes healthy from the
   rebuilt image and the application's health checks still pass. The
   PostgreSQL entrypoint prepares the local `pgbackrest` folder as private
   uid/gid `70:70`. Do not deploy the code directly to production before this
   dev acceptance.
2. Find the pgBackRest container, then create the stanza while PostgreSQL is
   running but WAL archiving is still disabled:

   ```bash
   sudo docker ps --format '{{.Names}}' --filter name=pgbackrest
   read -r -p 'pgBackRest container: ' PGBACKREST_CONTAINER
   sudo docker exec "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap stanza-create
   sudo docker exec "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap info
   ```

   Confirm `stanza-create` succeeds and `info` identifies the intended
   environment. Do not initialize production using a dev repository or vice
   versa.
3. Set `PGBACKREST_ENABLED=true` only after that succeeds, then redeploy.
   This restarts PostgreSQL and enables WAL archiving. Confirm the PostgreSQL
   logs show successful archive pushes and the pgBackRest logs show a
   successful archive check and initial full backup. Stop and investigate if
   PostgreSQL logs repeated `archive command failed` messages.
4. In that resource's environment settings, set `BACKUP_ENABLED=true`,
   `BACKUP_TARGET` to the environment name, and the appropriate heartbeat
   URLs. Set `BACKUP_INTERVAL_MINUTES=1440` (or leave it unset) for the daily
   logical dump. Configure dev and production separately.

The archive-check heartbeat is sent every 15 minutes only after a successful
`pgbackrest check`; its monitor should have a 15-minute period plus enough
grace for the check and deployment restart. The full-backup heartbeat is sent
only after a successful daily full backup; monitor it independently with a
daily period and runtime grace. The logical-bundle heartbeat is also daily.
Keep monitor URLs secret and do not ping them manually to simulate success.

## Off-site copies with Duplicati

Duplicati is the only off-site copier and should use the existing two
destinations. For each existing job, add both the `backups` folder and the
`pgbackrest` folder from the same resource. Do not select their parent, which
contains deployment settings and secrets.

- **Schedule**: run every 15 minutes. WAL is archived continuously and
  `archive_timeout` is 5 minutes; the archive-check monitor separately tests
  that the archiving path still works. Leave enough Duplicati runtime that
  successive runs do not overlap.
- **Exclusions**: for the logical folder, exclude `.govmap-backup-work-*`
  and `.govmap-backup.lock`. Do not exclude files from the pgBackRest
  repository.
- **Retention**: keep history, not just the latest copy. For example,
  `2D:U,14D:1D` keeps every version for 2 days, then one per day for 14 days.
  Keep the pgBackRest repository's Duplicati history at least as long as
  needed to recover an older version of the repository.
- **Encryption and credentials**: keep the passphrase and destination
  credentials outside the server, so a lost server does not take them with it.

pgBackRest compresses the local repository, and Duplicati may deduplicate
unchanged blocks, but do not assume the upload will be small. Measure the
repository size and Duplicati's transferred bytes after several daily full
backups. It is not point-in-time recovery off-site until the required WAL has
successfully reached Duplicati. The off-site recovery point is the newest
complete repository version that Duplicati has uploaded; local PITR is bounded
by the WAL archive delay (normally at most five minutes plus processing).

## Rehearse a pgBackRest point-in-time restore

Do this in dev or another isolated PostgreSQL 16 target, once from each
Duplicati destination. Restoring a repository is not proof of recovery; the
isolated PostgreSQL instance must actually start and reach the requested
target.

1. Use Duplicati to restore the complete `pgbackrest` source to a new private
   scratch directory. Do not write it over the live repository. Restore the
   logical `backups` folder separately if you also want to test the fallback.
2. Provide that scratch repository to a disposable PostgreSQL 16 container
   with the same pgBackRest configuration, a new empty data volume and the
   local socket directory. Never mount the live `postgres-data` volume. Ensure
   the scratch repository and new data volume are private and accessible to
   uid/gid `70:70`. Keep source API credentials and scheduled refreshes out of
   the isolated target.
3. Before starting PostgreSQL, run `pgbackrest --stanza=govmap info` against
   the restored repository and confirm it reports the expected stanza and a
   completed full backup. Then, with the disposable PostgreSQL data directory
   empty, restore to a UTC timestamp inside the available archive range:

   ```bash
   pgbackrest --stanza=govmap --type=time \
     --target='2026-11-11 12:00:00+00' --target-action=promote restore
   ```

   Replace the example timestamp with a known time in the recovered window.
   The command must finish successfully; do not run it against production or
   an existing data directory.
4. Start only the isolated PostgreSQL instance with the restored repository
   mounted at `/pgbackrest`. Use the GovMap database image, which already
   contains the config at `/etc/pgbackrest/pgbackrest.conf`; do not bind-mount
   it from the repository. Keep external routes and the worker
   disabled. Confirm PostgreSQL completes recovery and is promoted at or just
   after the requested target. Query the migration revision and representative
   row counts, then record the Duplicati destination, restored version,
   requested target, actual recovery time and results.
5. Stop the disposable instance and remove only the named scratch repository
   and data volume created for the rehearsal. Keep production database files
   and its pgBackRest repository untouched.

If the target predates the earliest retained full backup or required WAL,
restore to a later point or investigate the repository; do not call the drill
successful. A restored upstream request-budget ledger is stale: before using
the same source API keys, stop old callers and allow the documented 60-minute
drain with upstream requests disabled.

## Monitor and run a backup

Day to day, use the three heartbeat monitors, Duplicati's reports, available
disk space and both service logs. The logical backup log shows its daily
`Backup completed.`; the pgBackRest log shows archive checks and daily full
backup completion. The steps below are for shell access.

Find the running backup container's name:

```bash
sudo docker ps --format '{{.Names}}' --filter name=backup
```

In the **same Bash session**, enter it (this is not a credential):

```bash
read -r -p 'Backup container: ' BACKUP_CONTAINER
```

Check the schedule and recent results:

```bash
sudo docker logs --since 48h "$BACKUP_CONTAINER"
```

Find the pgBackRest container and inspect its recent archive-check and
full-backup results:

```bash
sudo docker ps --format '{{.Names}}' --filter name=pgbackrest
read -r -p 'pgBackRest container: ' PGBACKREST_CONTAINER
sudo docker logs --since 48h "$PGBACKREST_CONTAINER"
sudo docker exec "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap info
```

Check PostgreSQL's archiver counters and the local repository's free space:

```bash
sudo docker ps --format '{{.Names}}' --filter name=postgres
read -r -p 'PostgreSQL container: ' POSTGRES_CONTAINER
sudo docker exec "$POSTGRES_CONTAINER" psql --no-password -U govmap -d govmap -Atc \
  "SELECT current_setting('archive_mode'), current_setting('archive_timeout'), archived_count, failed_count, last_archived_wal, last_archived_time, last_failed_time FROM pg_stat_archiver"
```

```bash
PGBACKREST_HOST_DIR="$(sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/pgbackrest"}}{{.Source}}{{end}}{{end}}' "$PGBACKREST_CONTAINER")"; echo "${PGBACKREST_HOST_DIR:?no /pgbackrest mount found}"
df -h -- "$PGBACKREST_HOST_DIR"
du -sh -- "$PGBACKREST_HOST_DIR"
```

Repeated archive failures, a growing `pg_wal`, a missing heartbeat, or low
free space needs investigation before it threatens the database. The
4 GiB pgBackRest queue cap is a last-resort database-availability guard, not
a substitute for fixing storage or archive delivery.

Find the host path of the backup folder, then check the published bundle's
timestamp:

```bash
BACKUP_HOST_DIR="$(sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/backups"}}{{.Source}}{{end}}{{end}}' "$BACKUP_CONTAINER")"; echo "${BACKUP_HOST_DIR:?no /backups mount found}"
```

```bash
sudo ls -l --time-style=+%Y-%m-%dT%H:%M:%S%z "$BACKUP_HOST_DIR/govmap-backup.tar.gz"
```

To run a backup manually (for example after a configuration change), run it
as the backup user:

```bash
sudo docker exec --user 70:70 "$BACKUP_CONTAINER" govmap-backup
```

It prints the published path on success. A manual run replaces the previous
local bundle and sends a heartbeat when configured; ensure an older bundle
you need has been copied off-site first. It does not run the off-site job. A
manual monitor ping is not a backup test and can mask a missed run.

To check a new backup image in an environment with backups disabled (for
example dev before a release), don't enable backups or change the folder's
owner. A plain run there fails by design: `BACKUP_TARGET` is `unconfigured`
and the `backups` folder was never handed to the backup user. Instead, write
one throwaway bundle to a scratch directory in the container's `/tmp`, with
the heartbeat blanked so it can't ping another environment's monitor. `/tmp`
is memory-backed, so check the database size first:

```bash
sudo docker exec --user 70:70 "$BACKUP_CONTAINER" \
  psql -h postgres -U govmap -d govmap -Atc "select pg_size_pretty(pg_database_size(current_database()))"
```

If it's well under the host's free memory (about 1 GB or less), run:

```bash
sudo docker exec --user 70:70 -e BACKUP_TARGET=dev -e BACKUP_HEARTBEAT_URL= -e BACKUP_DIR=/tmp/backup-test \
  "$BACKUP_CONTAINER" bash -c 'mkdir -p "$BACKUP_DIR" && { govmap-backup; s=$?; rm -rf -- "$BACKUP_DIR"; exit $s; }'
```

Printing `/tmp/backup-test/govmap-backup.tar.gz` means the dump, its
`pg_restore --list` check, compression and the archive check all passed. The
scratch copy is then deleted. This doesn't test the schedule, the real
`backups` folder or the off-site job.

```bash
unset BACKUP_CONTAINER
```

```bash
unset PGBACKREST_CONTAINER POSTGRES_CONTAINER PGBACKREST_HOST_DIR
```

Keep `BACKUP_HOST_DIR` set if you will rehearse a restore from the local
bundle in this session; otherwise `unset BACKUP_HOST_DIR`.

## Rehearse a restore

Use only a trusted backup: restoring a PostgreSQL dump can execute SQL.
Perform database rehearsals on a **separate, isolated non-production**
PostgreSQL instance whose access controls and storage are suitable for the
data. Never replace the live database as a test. Check free space for the
compressed archive, extracted files and restored database.

Create a new private directory. If it already exists, stop and inspect it:

```bash
sudo mkdir -m 700 -- /srv/govmap-restore-test
```

Choose one source:

- **Local:** Copy the published bundle to the private directory, with
  `BACKUP_HOST_DIR` set as in
  [Monitor and run a backup](#monitor-and-run-a-backup) (the earlier
  host-timer bundle lives in its own configured directory):

  ```bash
  sudo cp -- "${BACKUP_HOST_DIR:?set BACKUP_HOST_DIR first}/govmap-backup.tar.gz" /srv/govmap-restore-test/govmap-backup.tar.gz
  ```

- **Off-site:** Use the backup product to restore the desired completed
  version of `govmap-backup.tar.gz` into `/srv/govmap-restore-test`, not its
  original location. The restore process must be authorized to write to the
  private directory. If it creates subdirectories, use the actual restored
  path in the extraction and cleanup commands.

Extract the trusted archive and verify its recorded checksums:

```bash
sudo mkdir -m 700 -- /srv/govmap-restore-test/unpacked
```

```bash
sudo tar --no-same-owner --no-same-permissions -xzf /srv/govmap-restore-test/govmap-backup.tar.gz -C /srv/govmap-restore-test/unpacked
```

```bash
sudo bash -c 'set -euo pipefail; cd /srv/govmap-restore-test/unpacked/govmap-backup; sha256sum --quiet -c SHA256SUMS; echo CHECKSUMS_OK'
```

Confirm the core files are present and nonempty:

```bash
sudo bash -c 'set -euo pipefail; cd /srv/govmap-restore-test/unpacked/govmap-backup; for f in database.dump logs.tar MANIFEST.txt RESTORE.txt SHA256SUMS; do if [[ ! -s "$f" ]]; then printf "ERROR: missing or empty %s\n" "$f" >&2; exit 1; fi; done; echo REQUIRED_FILES_OK'
```

Inspect the manifest privately. Compare the target or resource, timestamp,
PostgreSQL version and revision with the intended snapshot. Container bundles
record `deployment_config=not included`; earlier host-timer bundles may
include a configuration directory, possibly under a different name. When one
is included, check that the files you need are present and covered by the
recorded checksums.

```bash
sudo grep -E '^(created_utc|backup_target|resource_id|postgres_server_version|postgres_image|alembic_revision|[[:alnum:]_]+_config)=' /srv/govmap-restore-test/unpacked/govmap-backup/MANIFEST.txt
```

```bash
sudo find /srv/govmap-restore-test/unpacked/govmap-backup -mindepth 1 -maxdepth 1 -type d -name '*-config' -printf '%p\n'
```

If deployment configuration was included, confirm there is exactly one
matching directory and that its expected files are present. No match is
expected for container bundles or when configuration was deliberately
omitted.

`CHECKSUMS_OK` means the listed files match checksums stored in that same
bundle; it is not an independent signature or proof of a successful database
restore. Stop on a missing file, unexpected manifest, failed checksum or
uncertain target.

### Restore the database into scratch space

Use a compatible PostgreSQL version on the isolated instance. In the **same
Bash session**, enter the name of its running container; this is not a
credential. Verify the name and image belong to the isolated instance before
continuing:

```bash
read -r -p 'Isolated PostgreSQL container: ' RESTORE_PG
```

Reject an empty or invalid name:

```bash
if [[ "${RESTORE_PG:-}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then echo RESTORE_TARGET_NAME_VALID; else unset RESTORE_PG; echo 'ERROR: invalid container name' >&2; false; fi
```

```bash
sudo docker inspect --format '{{.Name}} {{.Config.Image}}' "$RESTORE_PG"
```

The container name and image alone do not prove isolation; verify the target
independently and stop if it is uncertain.

The following examples use the `govmap` PostgreSQL role and require its local
authentication to be configured already. Do not put a database password on
the command line. Create a new scratch database:

```bash
sudo docker exec -i "$RESTORE_PG" createdb --no-password --username=govmap govmap_restore_check && echo SCRATCH_CREATED
```

If creation fails or the database already exists, **stop**; do not drop an
existing database to make the test work. Only continue if this session
created the scratch database. Refresh sudo authentication and stream the
dump into it:

```bash
sudo -v
```

```bash
set -o pipefail; sudo cat -- /srv/govmap-restore-test/unpacked/govmap-backup/database.dump | sudo docker exec -i "$RESTORE_PG" pg_restore --no-password --username=govmap --no-owner --no-privileges --exit-on-error --dbname=govmap_restore_check && echo RESTORE_OK
```

Require `RESTORE_OK`. A failure can leave a partial scratch database; keep
it isolated while investigating. Check its revision and representative
counts:

```bash
sudo docker exec -i "$RESTORE_PG" psql --no-password --username=govmap --dbname=govmap_restore_check --set=ON_ERROR_STOP=1 --no-align --tuples-only --command='SELECT (SELECT version_num FROM alembic_version), (SELECT count(*) FROM members), (SELECT count(*) FROM bills), (SELECT count(*) FROM votes), (SELECT count(*) FROM zip_districts);'
```

Compare the revision with the bundle manifest and the counts with evidence
recorded for that snapshot. Counts alone do not prove every row is correct,
and a current live database may have changed since the dump.

### Clean up

After verification, confirm the container is still the isolated target and
remove **only the scratch database created by this rehearsal**:

```bash
sudo docker exec -i "$RESTORE_PG" dropdb --no-password --username=govmap govmap_restore_check && echo SCRATCH_DROPPED
```

```bash
unset RESTORE_PG
```

The extracted files include sensitive data. Remove only the specific paths
created for this rehearsal:

```bash
sudo rm -r -- /srv/govmap-restore-test/unpacked
```

```bash
sudo rm -- /srv/govmap-restore-test/govmap-backup.tar.gz
```

```bash
sudo rmdir -- /srv/govmap-restore-test
```

`rmdir` fails if anything else remains; inspect unexpected files instead of
deleting an unknown directory. If the restored archive was nested, remove
its exact path and then only the empty subdirectories.

## Recovery on another host

Full host recovery requires compatible infrastructure, the matching source
revision, separately retained credentials and an isolated deployment target.
First retrieve and verify an off-site bundle, then restore its database to a
new scratch target as above. Keep schedulers disabled and use a separate,
access-restricted test route while checking the recovered application.
Restoring logs, replacing a database and production cutover are separate
operator-approved operations; do not overwrite existing data or start a
second production connector. A successful scratch restore alone is not proof
that full host recovery has been rehearsed.

## Removing the earlier host timer

Before this service, a host systemd timer ran a root script through the
Docker socket, writing to its own directory with its own environment file.
That script and its unit files have been removed from the repository. To
remove an installed copy, first confirm the container service has published
a bundle, its heartbeat arrived and the off-site job now copies the new
folder. Then, one command at a time:

```bash
sudo systemctl disable --now govmap-daily-backup.timer
```

```bash
sudo systemctl is-active govmap-daily-backup.service
```

`inactive` (with a nonzero exit code) is expected; if it shows `active`, wait
for the run to finish. Show the installed unit files, including any drop-ins:

```bash
sudo systemctl cat govmap-daily-backup.service govmap-daily-backup.timer
```

Remove the files listed there, then reload systemd. Normally that is just
these two; if the output shows drop-in files (under a
`govmap-daily-backup.*.d/` directory), remove those as well:

```bash
sudo rm -- /etc/systemd/system/govmap-daily-backup.service /etc/systemd/system/govmap-daily-backup.timer
```

```bash
sudo systemctl daemon-reload
```

Remove the installed script and its private environment file (which holds
the old heartbeat URL), then the empty directory:

```bash
sudo rm -- /usr/local/sbin/govmap-daily-backup /etc/govmap-backup/daily.env
```

```bash
sudo rmdir -- /etc/govmap-backup
```

Keep the old local bundle until the replacement is proven recoverable from
off-site. A job that merely finished is not enough. Remove it only after all
of the following:

1. The off-site job's most recent run with the new folder reports success,
   with no errors or warnings, for each destination you rely on.
2. That destination lists a version of
   `govmap-backup.tar.gz` from the container's `backups` folder from that run.
3. That version, restored into scratch space as in
   [Rehearse a restore](#rehearse-a-restore), shows `CHECKSUMS_OK`,
   `REQUIRED_FILES_OK` and `RESTORE_OK`.
4. The off-site product still lists the old bundle's earlier versions, and its
   retention will keep them for as long as you may need them.

If any check fails or is uncertain, keep the old files and investigate. Then
remove the old local bundle and its lock file, followed by the empty
directory:

```bash
sudo rm -f -- /srv/govmap-backup/govmap-backup.tar.gz /srv/govmap-backup/.govmap-backup.lock
```

```bash
sudo rmdir -- /srv/govmap-backup
```

Confirm nothing remains:

```bash
systemctl list-unit-files 'govmap-daily-backup*' --no-pager
```

```bash
sudo ls -ld /etc/govmap-backup /usr/local/sbin/govmap-daily-backup /srv/govmap-backup
```

Expect `0 unit files listed.` and `No such file or directory` for each path.
If the old heartbeat check is not reused by the container service, delete or
pause it in the monitor so it does not alert.
