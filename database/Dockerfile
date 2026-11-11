# Keep the PostgreSQL base identical to the PaaS deployment image.
FROM postgres:16-alpine@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139

RUN apk add --no-cache pgbackrest \
    && mkdir -p /etc/pgbackrest

COPY entrypoint.sh /usr/local/bin/govmap-postgres-entrypoint
RUN chmod 755 /usr/local/bin/govmap-postgres-entrypoint

ENTRYPOINT ["/usr/local/bin/govmap-postgres-entrypoint"]
CMD ["postgres"]
