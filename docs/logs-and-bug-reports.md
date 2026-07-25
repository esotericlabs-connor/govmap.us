# Logs & bug reports (operator guide)

Two plain-text files capture everything you need to debug, and you grab them off
the box and attach them in chat. Both live on a persistent Docker volume, so they
survive redeploys.

## Where they are

Inside the backend container:

```
/app/logs/app.log          # runtime logs (errors, warnings, pipeline self-diagnostics)
/app/logs/bug_reports.log  # reports submitted from the site
```

They're kept on a named volume (`govmap-logs`) — a named volume rather than a
host path because the container runs as a non-root user, so it stays writable
where a root-owned bind mount wouldn't.

- **app.log** — everything the app itself logs (the `app.*` namespace): pipeline
  outcomes and self-diagnostics (HUD ZIP pages, committee-meeting keys, FEC
  rate-limit aborts), plus every warning and any unhandled 500 with its full
  traceback. Framework noise (uvicorn/SQLAlchemy) is excluded. Size-capped and
  rotated (`app.log`, `app.log.1`, …).
- **bug_reports.log** — one block per report submitted via the site's *Report a
  problem* button (or the error screen), each tagged `[Category / Subcategory]`
  so you can jump to the right area of the code. Example:

  ```
  ────────────────────────────────────────
  2026-07-24T22:14:03Z  [Finance / Itemized donations]
  URL: https://app.govmap.us/members/J000298/donations
  UA:  Mozilla/5.0 …
  Msg: The donation totals don't match the finance card.
  ```

Reports are **scrubbed on the way in** (HTML/angle-brackets stripped, control
characters and newlines collapsed, token-like strings redacted, length-capped)
and are only ever stored as plain text — never rendered as HTML — so they're
XSS-safe and can't forge log entries. Categories are a fixed allowlist
(`backend/app/report_categories.py`), so those fields can't be tampered with.

## Grab them for a chat

Copy a file out of the container to the current dir, then attach it:

```bash
docker cp govmap-backend:/app/logs/app.log ./app.log
docker cp govmap-backend:/app/logs/bug_reports.log ./bug_reports.log

# or just print one to read / pipe
docker compose exec backend cat /app/logs/bug_reports.log
```

## Clear them once resolved

Two independent commands (run in the backend container):

```bash
docker compose exec backend python -m app.logsctl clear-logs   # empties app.log (+ rotations)
docker compose exec backend python -m app.logsctl clear-bugs   # empties bug_reports.log
```

Clearing one never touches the other, and the app keeps logging straight into the
freshly-emptied file.
