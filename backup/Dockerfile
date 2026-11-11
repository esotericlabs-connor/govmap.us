# Base pinned by digest so a rebuild is reproducible and a re-pushed tag
# can't change what ships; Dependabot proposes digest bumps.
FROM alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

# PostgreSQL 16 client tools match the postgres:16 server; bash, GNU
# coreutils/findutils/tar and util-linux flock/setpriv match what the scripts
# are tested against. The zlib floor covers CVE-2026-4738 in the pinned base;
# a floor, not an exact pin, because Alpine carries only the newest revision.
RUN apk add --no-cache bash coreutils curl findutils flock postgresql16-client setpriv tar 'zlib>=1.4-r0'

ENV PATH="/usr/libexec/postgresql16:${PATH}" \
    HOME=/tmp

COPY entrypoint.sh /usr/local/bin/govmap-backup-entrypoint
COPY run.sh /usr/local/bin/govmap-backup-scheduler
COPY backup.sh /usr/local/bin/govmap-backup
RUN chmod 755 /usr/local/bin/govmap-backup-entrypoint /usr/local/bin/govmap-backup-scheduler /usr/local/bin/govmap-backup

# Starts as root only to prepare the backup directory; the entrypoint drops
# to uid/gid 70 before scheduling or running any backup.
ENTRYPOINT ["/usr/local/bin/govmap-backup-entrypoint"]
