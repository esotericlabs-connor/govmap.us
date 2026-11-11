FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
