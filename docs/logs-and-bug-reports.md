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

## Report ingress and capacity

The report endpoint compares the parsed scheme, hostname, and effective port
against `CORS_ORIGINS`; a lookalike hostname is not an allowed origin. Referer
fallback uses the same comparison. This is a browser-origin check, not
authentication: non-browser clients can supply an Origin header.

Report limits are 20 submissions per client address and 200 total submissions
per hour. They apply before Turnstile verification. Both are process-local,
reset on restart, and assume the current single-worker deployment. The global
limit prevents rotating client addresses from resetting the submission budget.
The bug-report log is still append-only; these limits do not replace operator
retention/cleanup.

`TRUSTED_PROXY_CIDRS` is empty by default. In that mode the socket peer determines
the address used for rate limiting; visitors behind the same proxy share its
20-report budget. `X-Forwarded-For` is never used. To enable per-visitor limits
behind the tunnel or the Next.js API proxy, configure only the actual proxy
peer addresses/networks whose ingress **overwrites** `CF-Connecting-IP` with the
verified visitor address. Do not trust an arbitrary LAN, client-controlled
proxy, or all addresses. Invalid CIDRs and `/0` networks fail configuration.
Malformed forwarded IPs fall back to the socket peer.

The backend container disables Uvicorn's proxy-header rewriting so this check
sees the actual socket peer. Use `--no-proxy-headers` for a manually launched
Uvicorn server too. Verify the direct API and same-origin Next.js ingress paths
separately in the deployment environment before adding trusted CIDRs; this
repository cannot establish the live Docker/tunnel peer addresses.

## Shared upstream capacity

Congress.gov, OpenFEC and bill-text downloads share outbound-attempt budgets
across on-demand requests, scheduled refreshes and manual jobs **within the
same process**. Defaults are 4 concurrent HTTP requests per source and hourly
limits of 4,500 Congress.gov attempts, 900 OpenFEC attempts and 600 bill-text
attempts. Every retry consumes an attempt. Settings are
`UPSTREAM_MAX_CONCURRENT_REQUESTS`, `CONGRESS_REQUESTS_PER_HOUR`,
`FEC_REQUESTS_PER_HOUR` and `GOVINFO_REQUESTS_PER_HOUR`.

On-demand operations are also bounded before they enter the worker-thread
queue. Cancellation does not free that capacity until the worker finishes.
Exhaustion returns HTTP 503 with `Retry-After` rather than a success-shaped
empty/partial response; refresh jobs fail explicitly and record an error.
Cached paths that need no upstream call remain usable.

Budgets reset on process restart. A separately launched manual refresh has its
own budget, so avoid concurrent CLI refreshes or multiple workers/replicas on
the same API key. Keep limits within the provider's verified key allowance and
retain an external edge rate limit for ingress; these controls are not a
distributed limiter. Donation requests reject unknown members and cycles that
are odd, outside 1976–2100, or later than the configured FEC cycle before
creating cache state.

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
