# GovMap backup service

This guide describes the repository's backup service without identifying a
particular host or deployment provider. It is intended for an operator who
needs to create, monitor and rehearse recovery of a GovMap backup.

**The simple contract:** GovMap prepares recoverable local copies of its
database, logs and approved non-secret configuration. The deployment operator
backs up **both** of the resource's `backups` and `pgbackrest` directories with
their external backup tool. GovMap does not configure destinations or hold
their decryption credentials. Ordinary website users do not administer backups.

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
   `GOVMAP_PGBACKREST_TIME_UTC` (default `03:30` UTC). pgBackRest expires
   backups
   using a seven-day time-based full-backup retention policy. Its repository
   is local to this resource, under `./pgbackrest`.
2. `backup` creates a separate logical `pg_dump` bundle, logs and non-secret
   recovery configuration daily at
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
repository-format change. Keep the shared config limited to options both
versions support: `archive-push-batch-size` is not recognized by the Alpine
3.22 sidecar and causes `info` to report an invalid configuration. Dev
acceptance and the restore rehearsal below are the proof (stanza, archive
check, full backup and restore). Review compatibility when either image is
updated; a version difference alone is not a reason to redesign working backups.

**Non-secret templates are included; actual secrets are not.** New logical
bundles contain `deployment-config/` with the source-controlled, unrendered
Compose template, pgBackRest configuration, database/backup image recipes,
this guide, the backup image's source commit and its effective backup switches
and schedules. The source files are baked into the image from an explicit
build-context allowlist, not exported from Coolify.

This is not a complete live-platform export. Recover other deployment
overrides, `.env` values, tunnel settings and credentials from the operator's
vault, which must be accessible independently of the server. Never archive
a rendered Compose configuration, full environment dump, or parent resource
directory. `source_commit=unknown` produces a warning and must not be treated
as verified configuration provenance.

**Start here:** [identify the environment](#identify-the-environment-first),
[enable backups](#bootstrap-pgbackrest), then select the two
[Duplicati sources](#off-site-copies-with-duplicati). For recovery, choose
[a logical dump](#rehearse-a-restore) or [a point in time](#rehearse-a-pgbackrest-point-in-time-restore).
Do not mirror a running PostgreSQL data directory; copy the consistent
artifacts GovMap produces.

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
- `GOVMAP_PGBACKREST_ENABLED=false` (the default): PostgreSQL archiving stays
  off and the pgBackRest scheduler idles. Do not turn it on until the stanza
  has been created; see [Bootstrap pgBackRest](#bootstrap-pgbackrest).
- `GOVMAP_PGBACKREST_ENABLED=true`: PostgreSQL archives WAL with a 5-minute
  `archive_timeout`. The sidecar runs `pgbackrest check` every 15 minutes and
  a full backup daily at `GOVMAP_PGBACKREST_TIME_UTC` (`03:30` UTC by
  default). It catches up at startup if no full backup exists or the last one
  is at least 24 hours old. Failed archive checks are logged and retried after
  15 minutes. Failed full backups are logged and retried every 15 minutes
  until one succeeds; neither failure sends its corresponding heartbeat.
- Stopping or redeploying the container interrupts a run in progress; the
  previous bundle is kept and the scratch directory is removed.
- Asynchronous archiving enables the `archive-push-queue-max=4GiB` safeguard.
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
| `GOVMAP_PGBACKREST_ENABLED` | `false` | Enables PostgreSQL WAL archiving and pgBackRest schedules; stanza must already exist |
| `GOVMAP_PGBACKREST_TIME_UTC` | `03:30` | Daily full backup time in UTC |
| `GOVMAP_PGBACKREST_ARCHIVE_HEARTBEAT_URL` | empty | Optional `https` heartbeat after each successful 15-minute archive check |
| `GOVMAP_PGBACKREST_BACKUP_HEARTBEAT_URL` | empty | Optional `https` heartbeat after each successful full backup |

Use the `GOVMAP_`-prefixed names exactly. pgBackRest reserves the
`PGBACKREST_` environment prefix for its own options, and Coolify injects its
configured environment variables into every Compose container. Remove any
old `PGBACKREST_ENABLED`, `PGBACKREST_TIME_UTC`,
`PGBACKREST_ARCHIVE_HEARTBEAT_URL` or `PGBACKREST_BACKUP_HEARTBEAT_URL`
variables from Coolify so pgBackRest does not interpret them as options.

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
| `MANIFEST.txt` | Creation time, backup target, PostgreSQL/`pg_dump` versions, observed Alembic revision, configuration format and source provenance |
| `deployment-config/` | Unrendered Compose template, pgBackRest configuration, image recipes, source commit, effective backup settings and this guide |
| `SHA256SUMS` | Checksums of the recorded files |
| `RESTORE.txt` | Basic restore notes for that bundle |

Bundles from the earlier host-timer script also contain a deployment
configuration directory and a different manifest layout. Use each bundle's
own manifest and restore notes.

The database dump and logs are collected separately, so they are not a single
transactionally synchronized snapshot. The bundle does not recreate the
operating system, deployment platform, off-site backup configuration,
external routes or policies, PostgreSQL cluster-wide roles, or the application
source tree. The recorded source commit belongs to the backup image; verify
it matches the deployment rather than assuming it does. Avoid deployments
during a backup; the Alembic revision queried after the dump is informational,
and the revision in the recovered database is authoritative. Keep source
access and recovery credentials independently of the server.

## Identify the environment first

Use host SSH, not a capability-restricted root terminal inside a container.
Start a disposable shell with `bash` first, so a failed guard ends only that
shell and returns you to your login shell. Errors must stop the sequence; do
not continue with empty variables. Copy the Compose project ID from the
intended Coolify resource, rather than identifying production as "the one
that isn't dev."

Fill in the quoted values before pasting. This guide deliberately avoids
interactive prompts in pasted blocks: a prompt would consume the next pasted
line as its answer. An empty value fails the checks below.

```bash
set -euo pipefail
RESOURCE_PROJECT=''   # Compose project ID from the intended Coolify resource
EXPECTED_TARGET=''    # dev or production
[[ "$RESOURCE_PROJECT" =~ ^[a-zA-Z0-9_-]+$ ]]
[[ "$EXPECTED_TARGET" =~ ^(dev|production)$ ]]

service_container() {
  local service="$1"
  local -a candidates
  mapfile -t candidates < <(sudo docker ps -q \
    --filter "label=com.docker.compose.project=$RESOURCE_PROJECT" \
    --filter "label=com.docker.compose.service=$service")
  if [[ ${#candidates[@]} -ne 1 ]]; then
    echo "ERROR: expected exactly one running $service container" >&2
    return 1
  fi
  printf '%s\n' "${candidates[0]}"
}

LIVE_PG="$(service_container postgres)"
BACKUP_CONTAINER="$(service_container backup)"
PGBACKREST_CONTAINER="$(service_container pgbackrest)"
ACTUAL_TARGET="$(sudo docker exec --user 70:70 "$PGBACKREST_CONTAINER" \
  sh -c 'printf "%s" "$BACKUP_TARGET"')"
[[ "$ACTUAL_TARGET" == "$EXPECTED_TARGET" ]]
sudo docker inspect --format '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}}' \
  "$LIVE_PG" "$BACKUP_CONTAINER" "$PGBACKREST_CONTAINER"
```

Names change on redeploy. Repeat this selection afterward. Never print a
complete container inspection or environment dump: both can contain secrets.

## Bootstrap pgBackRest

Do this in dev first on a reviewed, CI-green revision. Keep
`GOVMAP_PGBACKREST_ENABLED=false` during the initial deployment so PostgreSQL
starts without archiving while the repository is initialized.

1. In Coolify, remove the old `PGBACKREST_*` application variables and use
   the `GOVMAP_PGBACKREST_*` names from the settings table instead. Deploy the
   new PostgreSQL image and Compose services with
   `GOVMAP_PGBACKREST_ENABLED=false`. Confirm PostgreSQL becomes healthy from
   the rebuilt image and the application's health checks still pass. The
   PostgreSQL entrypoint prepares the local `pgbackrest` folder as private
   uid/gid `70:70`. Do not deploy the code directly to production before this
   dev acceptance.
2. Use [the guarded environment selection](#identify-the-environment-first),
   then create the stanza while PostgreSQL is running but WAL archiving is
   still disabled. Skip stanza creation if this resource's stanza already
   exists; `no valid backups` is not a missing stanza:

   ```bash
   sudo docker exec --user 70:70 "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap stanza-create
   sudo docker exec --user 70:70 "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap info
   ```

   Confirm the container's Compose project matches the intended Coolify
   resource, and its `BACKUP_TARGET` is the intended environment, before
   creating the stanza. `info` does not identify dev versus production by
   itself. It may report `status: error (no valid backups)` and
   `wal archive min/max: none present` at this stage; that is expected before
   the first backup and WAL archive. The commands must not emit invalid-option
   warnings. Do not initialize production using a dev repository or vice versa.
3. Set `GOVMAP_PGBACKREST_ENABLED=true` only after that succeeds, then redeploy.
   This restarts PostgreSQL and enables WAL archiving. Confirm the PostgreSQL
   logs show successful archive pushes and the pgBackRest logs show a
   successful archive check and initial full backup. Stop and investigate if
   PostgreSQL logs repeated `archive command failed` messages.
4. In that resource's environment settings, set `BACKUP_ENABLED=true`,
   `BACKUP_TARGET` to the environment name, and the appropriate heartbeat
   URLs. Set `BACKUP_INTERVAL_MINUTES=1440` (or leave it unset) for the daily
   logical dump. Configure dev and production separately.

Each environment has three scheduled jobs, so it needs three heartbeat checks
of its own. Never share a check between dev and production: a healthy dev ping
would hide a broken production job. Each job pings only after it succeeds.
Name each check `govmap-<env>-<job>` (for example `govmap-dev-…` and
`govmap-prod-…`):

| Check | Schedule (UTC) | Grace | Variable |
| --- | --- | --- | --- |
| `govmap-<env>-logical-backup` | Cron `30 2 * * *` | 1 hour | `BACKUP_HEARTBEAT_URL` |
| `govmap-<env>-archive-check` | Every 15 minutes | 10 minutes | `GOVMAP_PGBACKREST_ARCHIVE_HEARTBEAT_URL` |
| `govmap-<env>-pgbackrest-full` | Cron `30 3 * * *` | 2 hours | `GOVMAP_PGBACKREST_BACKUP_HEARTBEAT_URL` |

Set the cron checks' time zone to UTC and match any changed
`BACKUP_TIME_UTC` or `GOVMAP_PGBACKREST_TIME_UTC`. A new check stays "new"
until its first ping and cannot alert before then, so confirm each one turns
green after its first scheduled run. Keep the URLs secret (crop them from
screenshots) and do not ping them manually to simulate success.

## Off-site copies with Duplicati

Duplicati is the only off-site copier. Its job for a resource selects both the
`backups` folder and the `pgbackrest` folder from that resource. Do not select
their parent, which contains deployment settings and secrets.

To keep copies in more than one place, Duplicati 2.3.0.0 and later lets one job
have several destinations ("Add another destination"). It backs up to the
first destination, then after each successful run copies the backup files to
the others, so each destination can be restored on its own. Keep every
additional destination in the default `inline` mode so each run reaches all of
them; `interval` or `counting` mode leaves that destination with an older
recovery point. Older Duplicati versions need one job per destination with the
same two folders.

- **Schedule**: choose an interval based on the desired recovery point and
  measured runtime. Dev is configured for every 30 minutes; observe an
  automatic run and allow enough time for copies to all destinations before
  the next run. The five-minute WAL archive timeout, upload and copy time,
  and failures add delay, so the interval alone is not an off-site recovery
  guarantee.
- **Host service**: if Duplicati runs under systemd, enable it at boot and
  set a restart delay compatible with its start-rate limits. Verify behavior
  after a reboot; an enabled, active service does not prove that scheduled
  jobs or remote copies succeed.
- **UI access**: the packaged service runs as root, and its UI can read and
  restore any file and holds the destination credentials, so treat UI access
  as root access. Keep the default loopback-only listener and open it through
  an SSH tunnel (`ssh -N -L 8200:127.0.0.1:8200 <admin>@<host>`, then
  `http://127.0.0.1:8200`). Do not use `--webservice-interface=any` or
  `--webservice-allowed-hostnames=*`. Never leave `--webservice-password` in
  `DAEMON_OPTS`: `ps` and `systemctl status` show the command line. To set or
  change the password, add `DUPLICATI__WEBSERVICE_PASSWORD=<new>` to the
  root-only (`600`) `/etc/default/duplicati`, restart once, then delete that
  line and restart again; Duplicati keeps only a hash. Changing the password
  in the UI alone is not enough: a `--webservice-password` left in
  `DAEMON_OPTS` sets that old password again at every start. Keeping
  `--webservice-reset-jwt-config=true` in `DAEMON_OPTS` signs out existing
  browser sessions at each start.
- **Destination confidence**: Duplicati does not document how a failed
  copy to an additional destination affects the job result. A successful job
  and matching file timestamps alone do not prove that every destination has
  a complete, recoverable copy. An independent destination restore increases
  confidence, but the operator has deferred those separate drills for the
  current deployment. They are not a feature-development gate. Keep the
  configured copies and existing job-selected recovery evidence; do not
  describe untested destinations as independently verified.
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

## Prepare a new isolated restore target

Use this for either recovery method. It creates a **new** labeled volume,
never attaches live PGDATA, publishes no ports and supplies no application
credentials. Keep all steps for one rehearsal in the same Bash shell.
Check disk headroom for the restored repository, extracted dump and database.

On the existing host, first [identify the environment](#identify-the-environment-first)
and capture its immutable database image ID:

```bash
RESTORE_IMAGE="$(sudo docker inspect --format '{{.Image}}' "$LIVE_PG")"
```

On a replacement host without that container, build the compatible database
image from the matching trusted Git revision instead, then set `RESTORE_IMAGE`
to its `docker image inspect --format '{{.Id}}'` result. Do not substitute a
newer PostgreSQL major version for a physical restore.

```bash
[[ "$RESTORE_IMAGE" =~ ^sha256:[a-f0-9]{64}$ ]]
RESTORE_VERSION="$(sudo docker run --rm --network none --entrypoint postgres "$RESTORE_IMAGE" --version)"
[[ "$RESTORE_VERSION" == "postgres (PostgreSQL) 16."* ]]
printf '%s\n' "$RESTORE_VERSION"
REHEARSAL_ID="$(cat /proc/sys/kernel/random/uuid)"
RESTORE_PG="govmap-rehearsal-$REHEARSAL_ID"
RESTORE_VOLUME="govmap-rehearsal-$REHEARSAL_ID"
if sudo docker volume inspect "$RESTORE_VOLUME" >/dev/null 2>&1; then
  echo 'ERROR: rehearsal volume already exists' >&2
  exit 1
fi
sudo docker volume create --label "govmap.rehearsal=$REHEARSAL_ID" "$RESTORE_VOLUME"
sudo docker run --rm --network none --read-only --user 0:0 \
  --cap-drop ALL --cap-add CHOWN --cap-add FOWNER \
  --security-opt no-new-privileges:true --entrypoint sh \
  --mount "type=volume,src=$RESTORE_VOLUME,dst=/var/lib/postgresql/data,volume-nocopy" \
  "$RESTORE_IMAGE" -ceu '
    test -z "$(ls -A /var/lib/postgresql/data)"
    chmod 700 /var/lib/postgresql/data
    chown 70:70 /var/lib/postgresql/data
  '
RESTORE_ARGS=(
  --network none --read-only --user 70:70 --cap-drop ALL
  --security-opt no-new-privileges:true
  --label "govmap.rehearsal=$REHEARSAL_ID"
  --mount "type=volume,src=$RESTORE_VOLUME,dst=/var/lib/postgresql/data,volume-nocopy"
  --tmpfs /tmp:rw,nosuid,nodev,uid=70,gid=70,mode=700
  --tmpfs /var/run/postgresql:rw,nosuid,nodev,uid=70,gid=70,mode=700
)
REPOSITORY_ARGS=()

start_restore_target() {
  sudo docker run -d --name "$RESTORE_PG" "${RESTORE_ARGS[@]}" \
    "${REPOSITORY_ARGS[@]}" --entrypoint sh "$RESTORE_IMAGE" -ceu '
      printf "local all all trust\n" > /tmp/rehearsal_hba.conf
      exec postgres -D /var/lib/postgresql/data \
        -c archive_mode=off -c archive_command= -c listen_addresses= \
        -c unix_socket_directories=/var/run/postgresql \
        -c unix_socket_permissions=0700 -c hba_file=/tmp/rehearsal_hba.conf \
        -c logging_collector=off -c log_destination=stderr
    '
}

assert_restore_target() {
  [[ "$RESTORE_PG" == "govmap-rehearsal-$REHEARSAL_ID" ]]
  [[ "$RESTORE_VOLUME" == "govmap-rehearsal-$REHEARSAL_ID" ]]
  [[ "$(sudo docker inspect --format '{{index .Config.Labels "govmap.rehearsal"}}' "$RESTORE_PG")" == "$REHEARSAL_ID" ]]
  [[ "$(sudo docker inspect --format '{{.HostConfig.NetworkMode}}' "$RESTORE_PG")" == none ]]
  [[ "$(sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$RESTORE_PG")" == "$RESTORE_VOLUME" ]]
  [[ "$(sudo docker volume inspect --format '{{index .Labels "govmap.rehearsal"}}' "$RESTORE_VOLUME")" == "$REHEARSAL_ID" ]]
}
```

Require PostgreSQL **16** from the version command. The temporary `trust`
authentication applies only to this isolated container's private Unix socket,
not the live server or a network listener. The normal GovMap entrypoint is
deliberately bypassed so it cannot change a read-only recovery repository.
Do not start the target until completing the appropriate restore step below.

## Rehearse a pgBackRest point-in-time restore

Do this in dev or another isolated PostgreSQL 16 target. The normal Duplicati
job-selected restore is sufficient for the current operator-approved drill.
When its connection details are
available, Duplicati's **Restore** followed by **Direct restore from backup
files** can specify a particular destination. A normal job restore can also
exercise recovery, but does not independently verify a destination if the
source is unidentified. A small-file restore can check access and the
passphrase, but does not prove the full repository or its required WAL is
recoverable. Restoring the complete repository is not enough either: the
isolated PostgreSQL instance must actually start and reach the requested target.

1. Create a new private scratch directory. Stop if it already exists:

   ```bash
   sudo mkdir -m 700 -- /srv/govmap-pitr-test
   ```

   In Duplicati, choose **Restore**, select the job version, select the
   **complete** `pgbackrest` source, and restore it to a different location:
   `/srv/govmap-pitr-test`. Never restore over the original location.
   Duplicati 2.3 places the folder's contents (`backup/` and `archive/`)
   directly in that directory, as observed in the dev drill. Find where they
   landed:

   ```bash
   sudo find /srv/govmap-pitr-test -maxdepth 6 -type d \( -name backup -o -name archive \) -print
   ```

   If they are nested deeper, set `RESTORED_REPOSITORY` below to the exact
   directory that directly contains both.
2. [Prepare a new isolated target](#prepare-a-new-isolated-restore-target).
   Make only the **restored copy** accessible to uid 70; never run these
   permission commands against the live source:

   ```bash
   RESTORED_REPOSITORY=/srv/govmap-pitr-test
   [[ "$RESTORED_REPOSITORY" == /srv/govmap-pitr-test || "$RESTORED_REPOSITORY" == /srv/govmap-pitr-test/* ]]
   [[ "$(sudo realpath -e -- "$RESTORED_REPOSITORY")" == "$RESTORED_REPOSITORY" ]]
   sudo test -d "$RESTORED_REPOSITORY/backup"
   sudo test -d "$RESTORED_REPOSITORY/archive"
   sudo chown -hR 70:70 -- "$RESTORED_REPOSITORY"
   sudo chmod -R go-rwx -- "$RESTORED_REPOSITORY"
   REPOSITORY_ARGS=(--mount "type=bind,src=$RESTORED_REPOSITORY,dst=/pgbackrest,readonly")
   sudo docker run --rm "${RESTORE_ARGS[@]}" "${REPOSITORY_ARGS[@]}" \
     --entrypoint pgbackrest "$RESTORE_IMAGE" --stanza=govmap info
   ```

3. Select a completed full backup **before the target**, with the necessary
   WAL in this restored repository: `info`'s WAL maximum must be past the
   segment holding the first transaction after the target. Fill in its label
   from `info` and the known UTC target, including its offset:

   ```bash
   RESTORE_SET=''      # e.g. 20261111-172302F
   RESTORE_TARGET=''   # e.g. 2026-11-12 01:51:04.748183+00:00
   [[ "$RESTORE_SET" =~ ^[0-9]{8}-[0-9]{6}F$ ]]
   [[ -n "$RESTORE_TARGET" ]]
   sudo docker run --rm "${RESTORE_ARGS[@]}" "${REPOSITORY_ARGS[@]}" \
     --entrypoint pgbackrest "$RESTORE_IMAGE" --stanza=govmap \
     --set="$RESTORE_SET" --type=time --target="$RESTORE_TARGET" \
     --target-action=promote restore
   ```

   For an LSN drill, use `--type=lsn` and an explicitly recorded LSN such as
   `0/33000078` instead of a timestamp. Do not run a second restore into this
   populated volume. A clock-time target must follow the selected backup's
   completion and precede a later archived transaction's commit/abort record.
   WAL file timestamps do not establish that boundary.
4. Start the isolated database, inspect its log, and check its state:

   ```bash
   start_restore_target
   assert_restore_target
   for _ in $(seq 1 60); do
     state="$(sudo docker exec --user 70:70 "$RESTORE_PG" psql -h /var/run/postgresql -U govmap -d govmap -Atc 'SELECT pg_is_in_recovery()' 2>/dev/null || true)"
     [[ "$state" == f ]] && break
     sleep 5
   done
   sudo docker logs "$RESTORE_PG" 2>&1 | grep -E 'recovery stopping|selected new timeline|ready to accept|FATAL|PANIC' || true
   sudo docker exec --user 70:70 "$RESTORE_PG" \
     psql -h /var/run/postgresql -U govmap -d govmap -v ON_ERROR_STOP=1 -Atc \
     "SELECT pg_is_in_recovery(), current_setting('archive_mode'), current_setting('listen_addresses'), pg_last_xact_replay_timestamp();"
   ```

   The loop waits up to five minutes for promotion. A single early
   `FATAL: the database system is starting up` comes from the loop itself and
   is harmless. Require promotion (`f`), archiving `off`, an empty listen
   address and the log's correct stopping boundary (`recovery stopping before
   commit of transaction …` for the first transaction after the target, then
   `selected new timeline`). A server still recovering, or one that never
   reached its target, is not a pass.
5. Query the recovered schema and application data:

   ```bash
   sudo docker exec --user 70:70 "$RESTORE_PG" \
     psql -h /var/run/postgresql -U govmap -d govmap -v ON_ERROR_STOP=1 -Atc \
     'SELECT (SELECT version_num FROM alembic_version), (SELECT count(*) FROM members), (SELECT count(*) FROM bills), (SELECT count(*) FROM votes), (SELECT count(*) FROM source_runs);'
   ```

   Compare with the selected snapshot, not a newer live database. For the
   application-row drill also require **A, not B or the base value**.
   Record the job version, backup label, target, replay boundary and results;
   record the destination as unidentified if the UI did not identify it.
6. Follow [target cleanup](#remove-the-isolated-target), then remove only the
   known restored scratch copy:

   ```bash
   sudo rm -r -- "$RESTORED_REPOSITORY/backup" "$RESTORED_REPOSITORY/archive"
   sudo rmdir -- /srv/govmap-pitr-test
   ```

   If the repository was nested, `rmdir` fails; remove only the exact empty
   parent directories Duplicati created, deepest first. Never use a broad
   parent-directory deletion to make cleanup work.

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

First run [the guarded environment selection](#identify-the-environment-first)
in the same Bash session. It sets `LIVE_PG`, `BACKUP_CONTAINER` and
`PGBACKREST_CONTAINER` for exactly one verified environment. Do not pick
containers by name filters instead: `name=backup` also matches `pgbackrest`,
and every filter matches both environments.

Check the schedule and recent results:

```bash
sudo docker logs --since 48h "$BACKUP_CONTAINER"
```

Inspect pgBackRest's recent archive-check and full-backup results:

```bash
sudo docker logs --since 48h "$PGBACKREST_CONTAINER"
sudo docker exec --user 70:70 "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap info
```

Check PostgreSQL's archiver counters and the local repository's free space:

```bash
POSTGRES_CONTAINER="${LIVE_PG:?run the guarded environment selection first}"
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
is memory-backed, so check the database size first.

The guarded environment selection stops here because `BACKUP_TARGET` is
`unconfigured`. Select the dev backup container by its Compose project ID
instead. Copy that ID from the dev Coolify resource; this test is for dev
only:

```bash
set -euo pipefail
DEV_PROJECT=''   # Compose project ID copied from the dev Coolify resource
[[ "$DEV_PROJECT" =~ ^[a-zA-Z0-9_-]+$ ]]
mapfile -t DEV_BACKUP < <(sudo docker ps -q \
  --filter "label=com.docker.compose.project=$DEV_PROJECT" \
  --filter "label=com.docker.compose.service=backup")
[[ ${#DEV_BACKUP[@]} -eq 1 ]]
BACKUP_CONTAINER="${DEV_BACKUP[0]}"
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
unset PGBACKREST_CONTAINER POSTGRES_CONTAINER PGBACKREST_HOST_DIR DEV_PROJECT DEV_BACKUP
```

Keep `BACKUP_HOST_DIR` set if you will rehearse a restore from the local
bundle in this session; otherwise `unset BACKUP_HOST_DIR`.

When using Coolify's container terminal, check which user it selected. A
terminal opened as root in these capability-restricted containers may not
be able to read the private backup directory owned by uid 70. That does not
prove the bundle is missing. Prefer host-side `docker exec --user 70:70` for
backup inspections; a failed permission check must not be reported as an
empty or missing backup.

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
made before configuration-snapshot version 1 record
`deployment_config=not included`. New bundles include non-secret
`deployment-config/`; earlier host-timer bundles can contain a differently
named configuration directory and may contain sensitive configuration.
Inspect those privately. When configuration is included, check that the
required files are present and covered by the recorded checksums.

```bash
sudo grep -E '^(created_utc|backup_target|resource_id|postgres_server_version|postgres_image|alembic_revision|source_commit|deployment_config_version|[[:alnum:]_]+_config)=' /srv/govmap-restore-test/unpacked/govmap-backup/MANIFEST.txt
```

```bash
sudo find /srv/govmap-restore-test/unpacked/govmap-backup -mindepth 1 -maxdepth 1 -type d -name '*-config' -printf '%p\n'
```

If deployment configuration was included, confirm there is exactly one
matching directory and that its expected files are present. No match is
expected for older container bundles or when configuration was deliberately
omitted. Recover their configuration from the matching Git revision and
operator's vault; the older database dumps remain usable.

`CHECKSUMS_OK` means the listed files match checksums stored in that same
bundle; it is not an independent signature or proof of a successful database
restore. Stop on a missing file, unexpected manifest, failed checksum or
uncertain target.

### Restore the database into scratch space

After verifying the bundle, [prepare a new isolated target](#prepare-a-new-isolated-restore-target).
Do not reuse a PITR target or a live database. Initialize the empty volume
using the same PostgreSQL 16 image, then start only this isolated server:

```bash
sudo docker run --rm "${RESTORE_ARGS[@]}" --entrypoint initdb "$RESTORE_IMAGE" \
  -D /var/lib/postgresql/data -U govmap --auth=trust
start_restore_target
assert_restore_target
sudo docker logs --tail 30 "$RESTORE_PG"
sudo docker exec --user 70:70 "$RESTORE_PG" pg_isready -h /var/run/postgresql -U govmap
```

Wait for startup, then create a new scratch database:

```bash
assert_restore_target
sudo docker exec --user 70:70 "$RESTORE_PG" createdb --no-password \
  --host=/var/run/postgresql --username=govmap govmap_restore_check
echo SCRATCH_CREATED
```

If creation fails or the database already exists, **stop**; do not drop an
existing database to make the test work. Only continue if this session
created the scratch database. Refresh sudo authentication and stream the
dump into it:

```bash
sudo -v
```

```bash
assert_restore_target
sudo cat -- /srv/govmap-restore-test/unpacked/govmap-backup/database.dump |
  sudo docker exec -i --user 70:70 "$RESTORE_PG" pg_restore --no-password \
    --host=/var/run/postgresql --username=govmap --no-owner --no-privileges \
    --exit-on-error --dbname=govmap_restore_check
echo RESTORE_OK
```

Require `RESTORE_OK`. A failure can leave a partial scratch database; keep
it isolated while investigating. Check its revision and representative
counts:

```bash
sudo docker exec --user 70:70 "$RESTORE_PG" psql --no-password \
  --host=/var/run/postgresql --username=govmap --dbname=govmap_restore_check \
  --set=ON_ERROR_STOP=1 --no-align --tuples-only \
  --command='SELECT (SELECT version_num FROM alembic_version), (SELECT count(*) FROM members), (SELECT count(*) FROM bills), (SELECT count(*) FROM votes), (SELECT count(*) FROM zip_districts);'
```

Compare the revision with the bundle manifest and the counts with evidence
recorded for that snapshot. Counts alone do not prove every row is correct,
and a current live database may have changed since the dump.

### Clean up

After verification, [remove the isolated target](#remove-the-isolated-target).
There is no need to run `dropdb` against any live server.

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

## Remove the isolated target

Save the non-secret results first. Use the variables from the preparation
step; do not find a container or volume merely by a similar-looking name:

```bash
assert_restore_target
sudo docker stop "$RESTORE_PG"
sudo docker rm "$RESTORE_PG"
[[ "$(sudo docker volume inspect --format '{{index .Labels "govmap.rehearsal"}}' "$RESTORE_VOLUME")" == "$REHEARSAL_ID" ]]
sudo docker volume rm "$RESTORE_VOLUME"
unset RESTORE_PG RESTORE_VOLUME RESTORE_ARGS REPOSITORY_ARGS REHEARSAL_ID
```

If setup failed before creating a container, inspect the exact volume's label
and mounts before removing it separately. A missing label or unexpected mount
is a reason to stop, not to force removal. Never use volume pruning or a
wildcard to clean up a rehearsal.

## Prove an application-row rollback in dev

Do this once after the reviewed dev deployment passes CI. It uses an existing
bill and changes only its title and automatically updated timestamp. No new
table, endpoint or source identity is created. **Never run it in production.**

### 1. Stop dev writers

Record the original dev scheduler setting. Set dev's
   `SCHEDULER_ENABLED=false`, redeploy dev, and wait for old workers to stop.
   [Rediscover the environment](#identify-the-environment-first). Require
   `EXPECTED_TARGET=dev`, a successful archive check, and a completed full
   backup from before the test; record that backup's label. Ensure no other
   operator is running a refresh. Stop only the verified dev frontend/backend
   to prevent request-time enrichment while leaving the idle worker available:

   ```bash
   [[ "$EXPECTED_TARGET" == dev && "$ACTUAL_TARGET" == dev ]]
   DEV_WORKER="$(service_container worker)"
   DEV_BACKEND="$(service_container backend)"
   DEV_FRONTEND="$(service_container frontend)"
   DEV_SYSTEM_ID="$(sudo docker exec --user 70:70 "$LIVE_PG" \
     psql -h /var/run/postgresql -U govmap -d govmap -v ON_ERROR_STOP=1 -Atc \
     'SELECT system_identifier FROM pg_control_system();')"
   [[ "$DEV_SYSTEM_ID" =~ ^[0-9]+$ ]]
   sudo docker exec "$DEV_WORKER" python -c \
     'from app.config import settings; assert not settings.scheduler_enabled; assert settings.upstream_budget_scope == "worker"'
   sudo docker stop "$DEV_FRONTEND" "$DEV_BACKEND"
   ```

### 2. Save the original row

Choose one existing, fully enriched dev bill. Keep its original fields in
   a new private host directory **before any write**. The following temporary
   helper runs inside the idle worker, using its existing database connection.
   It never fetches from an upstream source or prints credentials. To list
   candidates (read-only):

   ```bash
   sudo docker exec --user 70:70 "$LIVE_PG" psql -h /var/run/postgresql -U govmap -d govmap -Atc \
     "SELECT bill_id, left(title, 60) FROM bills WHERE enriched_at IS NOT NULL ORDER BY enriched_at DESC LIMIT 5;"
   ```

   ```bash
   BILL_ID=''   # an existing, fully enriched dev bill, e.g. hr9381-119
   [[ "$BILL_ID" =~ ^[a-z]+[0-9]+-[0-9]+$ ]]
   umask 077
   ROW_TEST_DIR="$HOME/govmap-row-test"
   mkdir -m 700 -- "$ROW_TEST_DIR"
   cat > "$ROW_TEST_DIR/drill.py" <<'PY'
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select, update

from app.config import settings
from app.db import async_session_factory, engine
from app.models.bill import Bill


class BillChoice(BaseModel):
    bill_id: str = Field(pattern=r"^[a-z]+\d+-\d+$", max_length=20)


class State(BillChoice):
    title: str | None
    updated_at: AwareDatetime
    system_id: str
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")


class Change(BaseModel):
    phase: Literal["A", "B"]
    updated_at: AwareDatetime


def value(state: State, phase: str) -> str:
    return f"GovMap recovery {phase} {state.nonce}"


def emit(data: dict[str, str | int | None]) -> None:
    print(json.dumps(data), flush=True)


async def main() -> None:
    if settings.scheduler_enabled or settings.upstream_budget_scope != "worker":
        raise RuntimeError("Run only in the verified, idle dev worker")
    mode = sys.argv[1]
    async with async_session_factory() as db:
        control = func.pg_control_system().table_valued("system_identifier")
        system_id = str(await db.scalar(select(control.c.system_identifier)))
        if system_id != os.environ["GOVMAP_REHEARSAL_SYSTEM_ID"]:
            raise RuntimeError("Worker database is not the verified dev PostgreSQL instance")
        if mode == "capture":
            ident = BillChoice(bill_id=sys.argv[2])
            bill = await db.get(Bill, ident.bill_id)
            if bill is None or bill.enriched_at is None:
                raise RuntimeError("Choose an existing, fully enriched bill")
            state = State(
                bill_id=bill.bill_id, title=bill.title, updated_at=bill.updated_at,
                system_id=system_id, nonce=uuid4().hex,
            )
            print(state.model_dump_json(), flush=True)
            return

        state = State.model_validate_json(sys.stdin.readline())
        if state.system_id != system_id:
            raise RuntimeError("Database identity differs from the saved state")
        if mode == "expected-a":
            print(value(state, "A"), flush=True)
            return

        async def change(
            expected_title: str | None, expected_time: datetime,
            title: str | None, stamp: datetime | None = None,
        ) -> datetime:
            values: dict[str, str | datetime | None] = {"title": title}
            if stamp is not None:
                values["updated_at"] = stamp
            result = await db.execute(
                update(Bill)
                .where(
                    Bill.bill_id == state.bill_id,
                    Bill.title.is_not_distinct_from(expected_title),
                    Bill.updated_at == expected_time,
                )
                .values(**values)
                .returning(Bill.updated_at)
            )
            changed_at = result.scalar_one_or_none()
            if changed_at is None:
                raise RuntimeError("Row changed unexpectedly; refusing to overwrite it")
            await db.commit()
            return changed_at

        if mode == "mark":
            a_time = await change(state.title, state.updated_at, value(state, "A"))
            emit({"phase": "A", "updated_at": a_time.isoformat(), "value": value(state, "A")})
            target = await db.scalar(select(func.clock_timestamp()))
            await db.commit()
            emit({"target": target.isoformat(sep=" ")})
            await asyncio.sleep(2)
            b_time = await change(value(state, "A"), a_time, value(state, "B"))
            emit({"phase": "B", "updated_at": b_time.isoformat(), "value": value(state, "B")})
            lsn = await db.scalar(select(func.pg_switch_wal()))
            await db.commit()
            emit({"wal_switch_lsn": str(lsn)})
        elif mode == "cleanup":
            events = [json.loads(line) for line in sys.stdin if line.strip()]
            changes = [Change.model_validate(event) for event in events if "phase" in event]
            if not changes:
                raise RuntimeError("No recorded commit; inspect the row without forcing cleanup")
            last = changes[-1]
            await change(
                value(state, last.phase), last.updated_at, state.title, state.updated_at
            )
            bill = await db.get(Bill, state.bill_id)
            if bill is None or bill.title != state.title or bill.updated_at != state.updated_at:
                raise RuntimeError("Original row fields did not match after cleanup")
            remaining = await db.scalar(
                select(func.count()).select_from(Bill)
                .where(Bill.title.in_([value(state, "A"), value(state, "B")]))
            )
            if remaining != 0:
                raise RuntimeError("A rehearsal marker remains; inspect it before resuming")
            emit({"restored_bill": state.bill_id, "remaining_markers": remaining})
        else:
            raise RuntimeError("Unknown operation")


async def run() -> None:
    try:
        await main()
    finally:
        await engine.dispose()


asyncio.run(run())
PY
   (
     set -o noclobber
     sudo docker exec -i -e GOVMAP_REHEARSAL_SYSTEM_ID="$DEV_SYSTEM_ID" \
       "$DEV_WORKER" python -c "$(cat "$ROW_TEST_DIR/drill.py")" \
       capture "$BILL_ID" > "$ROW_TEST_DIR/row.json"
   )
   test -s "$ROW_TEST_DIR/row.json"
   sync -f -- "$ROW_TEST_DIR/row.json"
   ```

   Inspect `row.json` privately and confirm the bill ID/original fields.
   Do not overwrite this file or repeat capture after changing the row.

### 3. Write A and B around a recorded target

Commit A, record a database-clock target after A, then commit B after
   the target and switch WAL. Preserve the commit evidence:

   ```bash
   (set -o noclobber; : > "$ROW_TEST_DIR/changes.jsonl")
   sudo docker exec -i -e GOVMAP_REHEARSAL_SYSTEM_ID="$DEV_SYSTEM_ID" \
     "$DEV_WORKER" python -c "$(cat "$ROW_TEST_DIR/drill.py")" \
     mark < "$ROW_TEST_DIR/row.json" | tee -a "$ROW_TEST_DIR/changes.jsonl"
   sudo docker exec --user 70:70 "$PGBACKREST_CONTAINER" pgbackrest --stanza=govmap check
   ```

   Require A and B records, the target and a successful archive check.
   Do not rerun `mark`; an unexpected title/timestamp fails closed.

### 4. Recover the copied repository

Let the existing Duplicati job finish after these commits. Restore that
   complete repository once and follow the [PITR steps](#rehearse-a-pgbackrest-point-in-time-restore),
   using the **recorded pre-test full-backup label** and the exact `target`
   from `changes.jsonl`. Do not choose a newer full backup made after A.

### 5. Require the restored application value A

After the isolated instance reaches its target and promotes, verify the
   application value, not just counts or a WAL marker:

   ```bash
   EXPECTED_A="$(sudo docker exec -i -e GOVMAP_REHEARSAL_SYSTEM_ID="$DEV_SYSTEM_ID" \
     "$DEV_WORKER" python -c "$(cat "$ROW_TEST_DIR/drill.py")" expected-a \
     < "$ROW_TEST_DIR/row.json")"
   assert_restore_target
   sudo docker exec -i --user 70:70 "$RESTORE_PG" \
     psql -h /var/run/postgresql -U govmap -d govmap -v ON_ERROR_STOP=1 -At \
     -v bill_id="$BILL_ID" -v expected_a="$EXPECTED_A" <<'SQL'
SELECT count(*) = 1 FROM bills WHERE bill_id = :'bill_id' AND title = :'expected_a';
SQL
   ```

   Require `t`: the row is A, not B and not its original base-backup value.
   Keep the stopping-boundary log and this result as the recovery evidence.

### 6. Restore the original live dev fields

Use the saved timestamp guard:

   ```bash
   [[ "$EXPECTED_TARGET" == dev && "$ACTUAL_TARGET" == dev ]]
   { cat "$ROW_TEST_DIR/row.json"; cat "$ROW_TEST_DIR/changes.jsonl"; } |
     sudo docker exec -i -e GOVMAP_REHEARSAL_SYSTEM_ID="$DEV_SYSTEM_ID" \
       "$DEV_WORKER" python -c "$(cat "$ROW_TEST_DIR/drill.py")" cleanup
   ```

   Require `remaining_markers: 0`. Cleanup restores both the original title
   and `updated_at`. If a command failed after a commit but before its log
   reached the host, keep the private state and inspect the row; never remove
   the comparison guard to force a write.

### 7. Resume dev and remove rehearsal files

Start the same dev frontend/backend, restore the **original** scheduler
   setting through Coolify, and redeploy dev if that setting changed:

   ```bash
   sudo docker start "$DEV_BACKEND" "$DEV_FRONTEND"
   ```

   Rediscover containers and verify dev health. Clean the isolated target
   and its restored repository as above. Only after live cleanup succeeds:

   ```bash
   rm -- "$ROW_TEST_DIR/drill.py" "$ROW_TEST_DIR/row.json" "$ROW_TEST_DIR/changes.jsonl"
   rmdir -- "$ROW_TEST_DIR"
   ```

If recovery fails, preserve the evidence but still perform guarded live-row
cleanup and restore the intended dev service state. A failed drill is not
permission to leave test data in the application.

## Recovery on another host

Full host recovery requires compatible infrastructure, the matching source
revision, separately retained credentials and an isolated deployment target.

1. Retrieve a trusted off-site logical bundle and, for PITR, the complete
   repository version. Verify the bundle checksums and target. Preserve these
   restored sources unchanged throughout recovery.
2. Recover the recorded Git revision and the vault-held deployment settings.
   The snapshot contains templates, not the live platform or its secrets.
   Recreate Docker/Coolify, DNS/tunnel configuration and access policies from
   the operator's records. Keep all public routes and ingestion disabled.
3. Use the compatible PostgreSQL 16 image and one of the isolated restore
   procedures above. Require the expected schema and representative records,
   not just a healthy container. Start with code matching the recovered
   schema; apply later reviewed migrations only as an intentional upgrade.
4. Prepare a **new** application resource with new named storage. Stop its
   application writers before loading data. For a logical recovery, initialize
   its empty PostgreSQL cluster/role with the vault-held password and import
   into a new empty `govmap` database using `pg_restore --no-owner
   --no-privileges --exit-on-error`. For PITR, restore the selected backup to
   its verified-empty PGDATA while PostgreSQL is stopped; do not transplant a
   directory from a running rehearsal server. Keep the original resource and
   recovery sources untouched.
5. Keep `SCHEDULER_ENABLED=false`, archiving disabled and source credentials
   withheld while checking the recovered application's read-only views on
   an access-restricted route. PITR restores cluster roles/passwords from
   that point; reconcile them with the vault before connecting the app.
6. Before reusing upstream credentials, stop every old caller and allow a
   full 60-minute drain with upstream traffic disabled. Restore the request
   ledger with the database; do not clear it to bypass the drain.
7. Prepare the new resource's private backup directories. Initialize its
   **new, empty** pgBackRest repository, enable archiving through a controlled
   restart, and require a successful archive check and full backup. Do not
   initialize over the preserved recovery repository.
8. With operator approval, cut over the route, restore the intended worker
   setting, and configure this resource's two source directories in Duplicati.
   Confirm backups, heartbeats and an external copy before retiring old data.
   Restore old logs only to private archival storage, not over active logs.

A successful isolated database restore is not proof that whole-host recovery
or production cutover has been rehearsed.

## Verify automation, alerts and a real reboot

These are finite acceptance checks, not a requirement to keep repeating
successful restores. Reuse applicable logs from the final deployed version.

### Scheduled operation

1. Inspect the logical backup log for a real scheduled `Backup completed.`
   and the bundle's new timestamp. Check its manifest's known source SHA
   against the deployment and its `deployment-config/` checksums.
2. Inspect the pgBackRest log for a scheduled full backup and `info` for its
   new completed full entry. Require a real successful archive check too.
3. Match those completion times to the three real heartbeat checks. A manual
   success ping or container health alone does not prove any of these jobs ran.
4. Require a subsequent successful unattended Duplicati job that includes
   both source directories. Record its job/version/time and warnings/errors.
   A 30-minute schedule is not a guaranteed 30-minute off-site recovery point.

### Alert delivery

The operator already verified explicit failure-alert email delivery. For a
future retest, use a **disposable** Healthchecks check with the same email
integration: send that check's `/fail`, confirm its Down transition and email,
then remove the disposable check. Never put its secret URL in shell history
or a screenshot. Do not manually ping any of the three real checks.

An explicit failure proves alert delivery, not a missed-interval transition.
If a timer test is later needed, stop pinging a disposable check and wait for
its configured grace to expire. That additional test is not a current
closeout gate.

### Reboot the shared host

Only the operator performs this, during a confirmed maintenance window.

1. Confirm fresh successful backups and an external copy, vault access
   independent of this host, out-of-band console access, and no active
   deployment, backup or restore. Record any intentionally stopped services.
2. Inspect Duplicati's unit without dumping secret-bearing settings:

   ```bash
   sudo systemctl is-enabled duplicati.service
   sudo systemctl is-active duplicati.service
   sudo systemctl show duplicati.service \
     -p FragmentPath -p User -p Group -p Restart -p RestartUSec -p RequiresMountsFor
   cat /proc/sys/kernel/random/boot_id
   ```

   Verify the existing job/configuration and destination credentials are on
   persistent storage. Privately confirm any SMB/local mount is really
   mounted, not just an empty directory. Keep the established restart delay;
   change unit ordering only if actual dependencies require it.
3. After explicitly confirming the shared-host outage, the operator runs
   `sudo systemctl reboot`.
4. Reconnect and require a different boot ID, Duplicati automatically active,
   the same persisted jobs/settings, and usable source/destination mounts.
   Rediscover dev and production containers; require their intended health,
   matching release identities, schema, archiving and archive checks.
5. Let Duplicati start its next job itself and verify completion. Do not count
   a manual run or `is-enabled` alone as automatic recovery after reboot.

Do not change backup products, retention or destinations for this check.
Once the application-row drill, this reboot and the recorded scheduled cycle
pass alongside release CI, close backup engineering for the present
infrastructure. Reopen it for an infrastructure/persistence change, an actual
failure or a demonstrated capacity problem, not another identical exercise.

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
