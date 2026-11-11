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

COPY entrypoint.sh /usr/local/bin/govmap-backup-entrypoint
COPY run.sh /usr/local/bin/govmap-backup-scheduler
COPY pgbackrest-run.sh /usr/local/bin/govmap-pgbackrest-scheduler
COPY backup.sh /usr/local/bin/govmap-backup
COPY pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
RUN chmod 755 /usr/local/bin/govmap-backup-entrypoint /usr/local/bin/govmap-backup-scheduler /usr/local/bin/govmap-pgbackrest-scheduler /usr/local/bin/govmap-backup

# Starts as root only to prepare the backup directory; the entrypoint drops
# to uid/gid 70 before scheduling or running any backup.
ENTRYPOINT ["/usr/local/bin/govmap-backup-entrypoint"]
