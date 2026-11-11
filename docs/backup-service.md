# GovMap backup service

This guide describes the repository's backup service without identifying a
particular host or deployment provider. It is intended for an operator who
needs to create, monitor and rehearse recovery of a GovMap backup.

**Protect the backup:** A bundle is not encrypted on the server and contains
database contents and private logs. Keep it and any extracted copies in
private directories. Do not put credentials, passphrases, monitor URLs,
private hostnames or actual resource identifiers in the repository,
screenshots or support messages.

## What it does

The `backup` service in [docker-compose.PaaS.yml](../docker-compose.PaaS.yml)
runs inside the same Compose stack as the application. It is built from
[backup/](../backup/) and creates one compressed recovery bundle per day. It
is a logical PostgreSQL backup plus the backend logs, not a full server or
disk image. Each run:

1. Connects to the stack's `postgres` service by name with the stack's own
   database password. It needs no Docker socket and no host scripts.
2. Creates a consistent custom-format `pg_dump`, checks its table of contents
   with `pg_restore --list`, and archives the backend logs from a read-only
   mount of the log volume. An unreadable log file is skipped with a warning.
3. Writes a manifest, checksums and short restore notes. It builds the
   archive in a private scratch directory and atomically replaces the
   published file only when the new archive is complete. A failure leaves the
   previous published bundle in place.
4. Optionally sends a success heartbeat after publication. A failed heartbeat
   produces a warning but does not undo the backup.

The container starts as root only long enough to prepare its host directory,
then drops to uid/gid `70` (no capabilities) for the scheduler and every
backup. It has a read-only root filesystem, all other Linux capabilities
dropped and `no-new-privileges`. It uses PostgreSQL 16 client tools to match
the PostgreSQL 16 server.

**Deployment configuration and secrets are not included.** The `.env` values,
tunnel token and other credentials are kept in the operator's vault and must
be recoverable independently of the server.

### Destination

The bundle is written to `/backups` in the container. It is bind-mounted from
`./backups`, which the deployment platform resolves to a `backups` folder
inside **that resource's own directory** on the host. The platform rejects
variables in volume sources, and the relative path gives every resource
(production, test) its own folder automatically. No host setup is needed:
on first deploy the directory is created either root-owned (by Docker) or
owned by the platform's SSH user (when the platform pre-creates it), and the
entrypoint changes it to mode `700`, owner `70:70`. It does this only when
backups are enabled for a named target and the directory is root-owned or
empty; a non-empty directory owned by any other user is left alone.

A run refuses to start, and sends no heartbeat, unless `BACKUP_TARGET` names
the environment (lowercase letters, digits and hyphens, up to 32 characters,
not `unconfigured`) and the directory is a real directory owned by uid `70`.
Group or other access is removed automatically. The path stays the same
across redeploys, so the off-site job keeps copying the right folder. It
changes only if the resource is deleted and recreated; deleting a resource
can also delete its directory, so keep off-site copies.

Find the host path from the running container (see
[Monitor and run a backup](#monitor-and-run-a-backup)):

```bash
sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/backups"}}{{.Source}}{{end}}{{end}}' "$BACKUP_CONTAINER"
```

The resource's directory also holds its deployment settings, including
secrets. Point the off-site job at the `backups` folder only, never its
parent.

### Schedule

`backup/run.sh` is the container's entry point:

- `BACKUP_ENABLED` other than `true` (the default): it logs that backups are
  disabled and idles. Use this for test environments.
- `BACKUP_ENABLED=true`: it runs daily at `BACKUP_TIME_UTC` (`HH:MM`, UTC,
  default `02:30`). When the container starts, it runs a catch-up backup only
  if the published bundle is missing or at least 24 hours old, so routine
  redeploys do not each create a backup.
- A failed run is logged and the schedule continues; the missing heartbeat
  raises the alert. An invalid `BACKUP_TIME_UTC` stops the container with an
  error.
- Stopping or redeploying the container interrupts a run in progress; the
  previous bundle is kept and the scratch directory is removed.

Run only one enabled backup service per environment.

### Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKUP_ENABLED` | `false` | `true` turns on the daily schedule |
| `BACKUP_TARGET` | `unconfigured` | Environment name; recorded in the manifest and required before any run |
| `BACKUP_TIME_UTC` | `02:30` | Daily start time in UTC |
| `BACKUP_HEARTBEAT_URL` | empty | Private `https` dead-man's-switch URL; store it as a secret |

The heartbeat URL is passed to `curl` on stdin so its token never appears in
the process list. The database password comes from `POSTGRES_PASSWORD`.

### Bundle contents

The published file is `govmap-backup.tar.gz` in the backup directory. Only one
local bundle is retained; a successful run replaces it. A separate backup
product such as Duplicati can encrypt and copy that file off-site and retain
older versions. Its schedule, encryption, credentials, retention and failures
must be checked separately. The heartbeat does **not** prove an off-site copy
exists or can be restored. Exclude the temporary `.govmap-backup-work-*`
directories and the lock file from the off-site selection.

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

## Enable it for an environment

Use a reviewed, CI-green revision. Everything is configured in the deployment
platform; no shell access is needed. The examples use the target name
`production`.

1. In the deployment's environment settings for that resource only, set
   `BACKUP_ENABLED=true`, `BACKUP_TARGET=production` and the private
   `BACKUP_HEARTBEAT_URL`, then deploy. Leave other environments at the
   defaults; their `backups` folder stays empty.
2. The first start finds no bundle and runs a catch-up backup immediately.
   Check the backup service's logs in the deployment platform for
   `Backup completed.` and confirm the heartbeat monitor received a ping.
3. Find the host path (shown under the resource's persistent storage, or with
   the `docker inspect` command in [Destination](#destination)). In the
   off-site backup product, add that `backups` folder as a source, excluding
   `.govmap-backup-work-*` and `.govmap-backup.lock`.

Configure the heartbeat monitor for a daily check at `BACKUP_TIME_UTC` in UTC,
with a grace period that covers the backup's runtime. After that, redeploys
need no backup steps: the folder, schedule and heartbeat carry over.

## Monitor and run a backup

Day to day, the heartbeat monitor and the off-site product's own reports are
the checks; the deployment platform's log view for the backup service shows
`Backups enabled for target "production"`, a `Next backup at` line and
`Backup completed.` after each run. The steps below are for shell access.

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
