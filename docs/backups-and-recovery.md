# GovMap backups and recovery

These are operator procedures for the Linux server and an **isolated recovery
host**. The scripts do not configure Duplicati, create a schedule, access a
remote host, or remove old backups. They have not yet been exercised against a
real server and must be reviewed and verified before being relied upon.

## What must be protected

- The repository and its `.env` contain application files and credentials.
- PostgreSQL data is in the `postgres-data` Docker volume, not in the repository.
- Application and bug-report logs are in the `govmap-logs` Docker volume.
- Duplicati configuration, its passphrase, and the age identity must be kept
  securely and separately from the backups. Losing either required key can make
  the corresponding backup unrecoverable.

Do **not** rely on a file copy of a running PostgreSQL data directory as a
consistent database backup. Use the encrypted `pg_dump` described below; it
captures a consistent database snapshot. Duplicati can back up that file along
with the application files and the log-volume files. Do not restore a copied
live PostgreSQL data directory over a database.

The database dump covers the GovMap database, not PostgreSQL cluster-wide roles,
server settings, the operating system, or other applications. The restore helper
uses the current single-owner Compose setup and does not restore original grants
or ownership. Review additional roles and grants separately if the deployment
changes.

## Prerequisites and keys

- Linux, Bash, GNU tar and coreutils, Docker with Compose, and `age` must be
  available on the applicable host. The scripts use only a local Unix-socket
  Docker context and reject `DOCKER_HOST` and `DOCKER_CONTEXT` overrides. A Unix
  socket can still be forwarded, so the operator must verify which daemon and
  host it reaches.
- Verify the selected Compose project and its `postgres` and `backend`
  containers before backup or restore. Compose project selection can be
  affected by `COMPOSE_PROJECT_NAME` and the restored directory name; the
  scripts do not prove that the selected project is the intended one.
- The database service must be running for a backup. The full archive also
  requires the existing backend container's named log volume and a locally
  available `postgres:16-alpine` image; it does not pull an image.
- Create an age identity on a separate trusted machine. Keep the private
  identity offline or in separate protected storage, never in the repository or
  Duplicati's source directories. Copy only its **public recipient** to a
  readable recipients file on the server. Restrict key-file permissions.
- Choose an existing writable backup directory outside the repository, on a
  filesystem that supports hard links. Do not allow untrusted users to modify
  that directory. The scripts use an atomic hard link to publish a completed
  backup without replacing an existing path; this does not guarantee storage
  durability after a power loss. Store copies in a separate location under your
  control, and configure retention and disk-space monitoring. The examples
  below use illustrative paths; choose your own. Do not expose keys, `.env`,
  archives, or logs in chat or CI.

For example, on the separate trusted machine, an operator can generate an age
identity and derive its public recipient:

```bash
umask 077
age-keygen -o /secure/location/govmap-backup.agekey
age-keygen -y /secure/location/govmap-backup.agekey > /secure/location/govmap-backup.recipients
```

Protect the recipients file from modification by untrusted users, and verify
**every** listed recipient against its intended identity through a trusted
channel before each backup, and prevent changes while the list is being copied.
Every listed recipient can decrypt the data; an unauthorized added or
substituted recipient exposes it. The full archive uses one private scratch
copy of this list for all three encryption steps so a later rotation cannot
silently change keys between components.
Verify that each required private identity is available separately. Age
encryption protects archive contents but does not by itself prove who created
an archive; restore only trusted backups. PostgreSQL dumps can execute SQL
during restoration, so validate the source and use the isolated recovery host.

## On-demand encrypted GovMap archive

After the prerequisites and destination are in place, an operator can run:

```bash
bash /opt/govmap/scripts/backup-govmap.sh \
  --destination /srv/govmap-backups \
  --recipients-file /etc/govmap/backup.recipients
```

On success the command prints the path to one new `govmap-*.tar.age` file.
It contains:

1. `app/`: the repository, including `.env` and `.git`.
2. `database.dump.age`: a separately encrypted, consistent PostgreSQL dump.
3. `logs.tar.age`: separately encrypted application and bug-report logs.

The repository's `.venv`, `backend/.venv`, `backend/data/staging`,
`frontend/node_modules`, `frontend/.next`, and `__pycache__` directories are
excluded. Symlinks are archived as links, not followed; separately protect any
needed targets outside the repository. The archive is not an operating-system
or full-server image.

Database and log intermediates are encrypted before being written; the outer
archive is also streamed through age. The scratch directory also contains the
public recipients list. Files are created with restrictive permissions, and an
existing backup is never overwritten. Failure returns a nonzero status and
removes the known temporary files when possible. A power loss or forced
termination can leave a `.govmap-*` scratch directory with encrypted
intermediates and the public recipients list, or a `.govmap-db-*` temporary
file. Inspect and remove only the specific abandoned path after confirming no
backup is running. A backup may already have been published if interruption
occurs during cleanup. Monitor free space; no retention is applied automatically.

Pause deployments and schema changes during either backup method so application
files and the database snapshot correspond to the same release. Logs and
application files are captured at different times from the database, not in
one atomic server-wide snapshot. Log files can change or rotate while they are
copied. For a stable log capture, the operator must quiesce log writers or use
a suitable filesystem snapshot; stopping the backend affects availability.
The scripts do not stop or start services.

## Fresh database snapshots for Duplicati

The database-only command is suitable for a required Duplicati pre-backup
script. It writes one new encrypted `.dump.age` file and prints its path:

```bash
bash /opt/govmap/scripts/backup-database.sh \
  --destination /srv/govmap-backups \
  --recipients-file /etc/govmap/backup.recipients
```

Configure the Duplicati job to include the application directory, including
`.env` and any required hidden files, the selected database-dump directory, and
the host path of the persistent log volume. Inspect the actual backend mount
and Docker volume to determine the log path; do not assume a particular Docker
data directory or volume driver. The Duplicati process must be able to read
all three sources. Exclude the live PostgreSQL volume from any restore procedure.
Its own destination, encryption, retention, and access controls are operator
choices.

After the reviewed scripts are available on the server, set these Duplicati
advanced options for paths without spaces, substituting the chosen paths:

```text
run-script-before-required = /bin/bash /opt/govmap/scripts/duplicati-database-hook.sh --destination /srv/govmap-backups --recipients-file /etc/govmap/backup.recipients
run-script-with-arguments = true
run-script-timeout = 30m
```

The timeout is an example, not a measured limit; choose one long enough for the
actual database size. The wrapper returns zero only when the dump command
succeeds and maps failures to exit code 5, which avoids success-like exit codes
in Duplicati's documented script conventions. Verify on the installed Duplicati
version that a failed hook and a timeout both abort the job and are reported as
failures. The default script timeout is only 60 seconds, and a timed-out script
can continue running: investigate it before starting another backup. See the
[Duplicati script documentation](https://docs.duplicati.com/automation-and-integration/scripts.md).

Confirm that the resulting Duplicati backup actually contains the newly
created dump, `.env`, and log files; a successful hook alone does not establish
that source filters or permissions included them. The hook's executable paths
and tools must be available to the Duplicati process itself. If Duplicati runs
in a container, its filesystem and Docker access must be configured
deliberately; host paths do not automatically exist inside it.

The Duplicati service identity needs permission to read the recipients file and
write the destination, plus access to the local Docker daemon. Docker daemon
access is effectively administrative access; grant it deliberately, not
broadly. The dump is already encrypted, and Duplicati should also encrypt its
own backup. Each run creates a new local dump; configure and monitor retention
and remove old local snapshots only after independently verifying retained
backups. The scripts never delete them.

## Restore on a separate host

1. Restore the repository, `.env`, a recent encrypted database dump, and the
   log-volume files with Duplicati to a **new staging location** on a separate,
   isolated recovery host. Keep `.env`, keys, and restored logs private. Do not
   overwrite the live server or reuse a copied live PostgreSQL data directory.
   Prevent the restored tunnel credentials, scheduler, and API keys from
   reaching production or external services during the rehearsal.
2. Ensure the restored code and database dump are from compatible releases.
   Select and verify the recovery Compose project consistently for every
   command. This Compose file uses fixed container names, so keep the recovery
   host separate from other deployments. The deploy script fetches the latest
   `main` and starts services, so do not run it as a recovery shortcut before
   checking the intended version.
3. Initialize a **fresh** Compose PostgreSQL volume and start only `postgres`;
   leave the backend, frontend, tunnel, and scheduler stopped. Ensure no other
   client can connect to the target database. Preserve any previous volume
   separately; the helper never deletes one.
4. On that recovery host, run the helper against the restored dump:

   ```bash
   bash scripts/restore-database.sh \
     --backup /secure/staging/govmap-db-EXAMPLE.dump.age \
     --identity-file /secure/keys/govmap-backup.agekey \
     --confirm-isolated-empty-target
   ```

   It checks that the backend is stopped, fully decrypts the input once before
   attempting a restore, and checks for non-system schemas, public relations,
   routines and types, non-default extensions, and other connections to the
   target database. These checks do not prove the database is empty: other
   database-level objects and settings are not covered. `pg_restore` runs
   without `--clean` or `--create` and uses one transaction with errors fatal.
   The isolation and empty-target flag is the operator's assertion; the script
   cannot prove the host is isolated or prevent another client from connecting
   after its check. Use a newly initialized target and keep all other clients
   stopped. If anything fails, keep the backend stopped and inspect the target
   before retrying.
5. Restore the staged log files into the **new** log volume while the backend
   is stopped, and verify that the backend's `appuser` can read and write them.
   Do not assume a host UID or overwrite another deployment's volume.
6. Verify the restored Alembic revision against the intended code, compare
   representative table counts and relationships with known-good expectations,
   and test the application on the isolated host. Review ownership/grants and
   `.env` permissions before any operator-approved cutover. Record the time and
   result of the restore rehearsal.

For a manual `govmap-*.tar.age` archive instead of Duplicati, first create a new
empty, private staging directory on encrypted storage. On an isolated host, a
trusted archive can be unpacked with:

```bash
umask 077
set -o pipefail
age --decrypt --identity /secure/keys/govmap-backup.agekey /secure/staging/govmap-EXAMPLE.tar.age \
  | tar --extract --file=- --directory /secure/empty-recovery-directory \
      --no-same-owner --no-same-permissions --keep-old-files
```

The directory receives `app/`, `database.dump.age`, and `logs.tar.age`. The
database dump can be passed to the restore helper. Decrypt the logs into a
separate new, empty private staging directory:

```bash
umask 077
set -o pipefail
age --decrypt --identity /secure/keys/govmap-backup.agekey /secure/empty-recovery-directory/logs.tar.age \
  | tar --extract --file=- --directory /secure/empty-log-staging-directory \
      --no-same-owner --no-same-permissions
```

Inspect the staged logs and restore them to the new log volume as above.
Restored application files and logs are plaintext on the recovery host, so that
host's storage and access must be protected. If decryption or extraction fails,
treat every extracted file as incomplete and do not use the partial recovery.

Creating an archive is not proof of recoverability. Group 0 remains blocked
until an actual backup is stored separately and an isolated restore has been
verified.
