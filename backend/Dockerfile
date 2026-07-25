FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create the operator log dir so the named `govmap-logs` volume mounted
# here inherits appuser ownership (a non-root container can't write a
# root-owned mount). Holds app.log + bug_reports.log at runtime.
RUN mkdir -p /app/logs

# Drop root inside the container. chown so the pipeline can write staging JSON
# under /app/data and the log files under /app/logs at runtime.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Apply migrations, then serve. Single-instance deploy, so running the
# migration on start is safe; revisit if this ever scales horizontally.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
