# Base pinned by digest so a rebuild is byte-for-byte reproducible and a
# re-pushed tag can't change what ships; Dependabot proposes digest bumps.
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# The pinned base can lag Debian security updates. Enforce a floor rather than
# an exact version: Debian's mirrors carry only the newest revision, so an
# exact pin breaks the build as soon as the next update supersedes it. Drop
# this once a base digest bump ships at least this zlib1g.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && v="$(dpkg-query -W -f='${Version}' zlib1g)" \
    && { dpkg --compare-versions "$v" ge '1:1.3.dfsg+really1.3.1-1+deb13u1' \
         || { echo "zlib1g $v predates the CVE-2026-76844/CVE-2026-85091 fix" >&2; exit 1; }; } \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --require-hashes refuses any package, transitive ones included, that isn't in
# the lock with a matching hash, so the image installs exactly what CI audited.
# The packaging toolchain is only needed to install; nothing imports it at
# runtime, so remove it rather than ship (and patch) it in production.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip uninstall --no-cache-dir -y setuptools wheel pip

COPY . .

ARG SOURCE_COMMIT=unknown
ENV APP_COMMIT_SHA=$SOURCE_COMMIT
RUN python -c "import os, re; sha = os.environ['APP_COMMIT_SHA']; assert re.fullmatch(r'unknown|[a-f0-9]{40}', sha), 'SOURCE_COMMIT must be a full Git SHA or unknown'"

# Pre-create the operator log dir so the named `govmap-logs` volume mounted
# here inherits appuser ownership (a non-root container can't write a
# root-owned mount). Holds app.log + bug_reports.log at runtime.
# Drop root inside the container. Only the runtime-writable directories (staging
# JSON under /app/data, logs under /app/logs) belong to appuser; the code stays
# root-owned so a compromised process cannot rewrite the application.
RUN mkdir -p /app/logs /app/data/staging \
    && useradd -m appuser \
    && chown -R appuser:appuser /app/logs /app/data
USER appuser

EXPOSE 8000

# Apply migrations, then serve. Single-instance deploy, so running the
# migration on start is safe; revisit if this ever scales horizontally.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]
