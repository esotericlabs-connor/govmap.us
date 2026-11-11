FROM alpine:3.22

# PostgreSQL 16 client tools match the postgres:16 server; bash, GNU
# coreutils/findutils/tar and util-linux flock/setpriv match what the scripts
# are tested against.
RUN apk add --no-cache bash coreutils curl findutils flock postgresql16-client setpriv tar

ENV PATH="/usr/libexec/postgresql16:${PATH}" \
    HOME=/tmp

COPY entrypoint.sh /usr/local/bin/govmap-backup-entrypoint
COPY run.sh /usr/local/bin/govmap-backup-scheduler
COPY backup.sh /usr/local/bin/govmap-backup
RUN chmod 755 /usr/local/bin/govmap-backup-entrypoint /usr/local/bin/govmap-backup-scheduler /usr/local/bin/govmap-backup

# Starts as root only to prepare the backup directory; the entrypoint drops
# to uid/gid 70 before scheduling or running any backup.
ENTRYPOINT ["/usr/local/bin/govmap-backup-entrypoint"]
