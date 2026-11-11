# Same PostgreSQL 16 base digest as docker-compose.yml and the CI service
# containers.
FROM postgres:16-alpine@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139

# Alpine's pgbackrest package depends on the generic `postgresql` provider,
# which apk would satisfy with a second, newer PostgreSQL server beside the
# official 16 build. The empty virtual package satisfies that dependency
# instead (apk's "creating empty virtual package" warning is expected). The
# floors cover fixed CVEs in the pinned base; drop each once a base digest
# bump ships at least that version.
RUN apk add --no-cache --virtual postgresql=16.0 \
    && apk add --no-cache pgbackrest \
        'zlib>=1.4-r0' 'libxslt>=1.1.43-r4' 'krb5-libs>=1.22.3-r0'

# Baked in rather than bind-mounted: Coolify resolves relative bind sources on
# the host, where repository files don't exist, so a file mount becomes an
# empty directory and the container fails to start. Must stay identical to
# backup/pgbackrest.conf (a unit test enforces it).
COPY pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
COPY entrypoint.sh /usr/local/bin/govmap-postgres-entrypoint
RUN chmod 755 /usr/local/bin/govmap-postgres-entrypoint

ENTRYPOINT ["/usr/local/bin/govmap-postgres-entrypoint"]
CMD ["postgres"]
