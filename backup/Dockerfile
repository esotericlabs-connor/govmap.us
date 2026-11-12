# Base pinned by digest so a rebuild is reproducible and a re-pushed tag
# can't change what ships; Dependabot proposes digest bumps.
FROM alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

# PostgreSQL 16 client tools match the server; server utilities provide
# pg_controldata, which pgBackRest needs to inspect the mounted data directory.
# jq reads backup metadata for catch-up scheduling. The zlib floor covers
# CVE-2026-4738 in the pinned base; Alpine carries only the newest revision.
RUN apk add --no-cache bash coreutils curl findutils flock jq pgbackrest postgresql16 postgresql16-client setpriv tar 'zlib>=1.4-r0'

ENV PATH="/usr/libexec/postgresql16:${PATH}" \
    HOME=/tmp

COPY backup/entrypoint.sh /usr/local/bin/govmap-backup-entrypoint
COPY backup/run.sh /usr/local/bin/govmap-backup-scheduler
COPY backup/pgbackrest-run.sh /usr/local/bin/govmap-pgbackrest-scheduler
COPY backup/backup.sh /usr/local/bin/govmap-backup
COPY backup/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
RUN chmod 755 /usr/local/bin/govmap-backup-entrypoint /usr/local/bin/govmap-backup-scheduler /usr/local/bin/govmap-pgbackrest-scheduler /usr/local/bin/govmap-backup

# Unrendered, source-controlled recovery files only; never copy a platform
# environment export or mount deployment files from the Coolify host.
COPY docker-compose.PaaS.yml /usr/local/share/govmap-recovery/docker-compose.PaaS.yml
COPY backup/pgbackrest.conf /usr/local/share/govmap-recovery/pgbackrest.conf
COPY database/Dockerfile /usr/local/share/govmap-recovery/database.Dockerfile
COPY backup/Dockerfile /usr/local/share/govmap-recovery/backup.Dockerfile
COPY docs/backup-service.md /usr/local/share/govmap-recovery/backup-service.md
ARG SOURCE_COMMIT=unknown
RUN bash -eu -c '[[ "$SOURCE_COMMIT" =~ ^(unknown|[a-f0-9]{40})$ ]] || { echo "SOURCE_COMMIT must be a full Git SHA or unknown" >&2; exit 1; }; printf "%s\n" "$SOURCE_COMMIT" > /usr/local/share/govmap-recovery/source-commit.txt'

# Starts as root only to prepare the backup directory; the entrypoint drops
# to uid/gid 70 before scheduling or running any backup.
ENTRYPOINT ["/usr/local/bin/govmap-backup-entrypoint"]
