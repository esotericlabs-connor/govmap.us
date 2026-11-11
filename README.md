# GovMap.us

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/75e24029-21c9-4501-9e41-4b97de882381" />

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/cb86aa69-3cde-4e54-b2e0-44500704efd0" />


A mobile-first web app that makes the entire US federal government easy to understand for everyday Americans. GovMap presents real, verified, public data — who represents you, how they vote, who runs the agencies that govern you, where the money goes, and how a bill moves from introduction through signing through judicial challenge — in a clean, digestible format, extended to the full process of American government.


> From City Council to Congress.

**Status:** pre-launch. The federal legislative application is running on a self-hosted platform at **https://govmap.us**. See [CODE-MANIFEST.md](CODE-MANIFEST.md) for the current build log and phase checklist.

The [platform roadmap](docs/platform-roadmap.md) proposes the next hardening
and data-expansion waves: federal coverage and history, then state and local,
with explicit correctness, security and release gates.

## Mission

Apathy is largely a UX problem. - Govmap.us aims to be a modern, nonpartisan, transparent civic tool that gives every American a clear, real-time view of their entire federal government — who represents them, how they vote, who runs the agencies that govern them, where the money goes, and how laws move through all three branches.

## Critical design principles

- **Nonpartisan above all else** — the moment it looks politically aligned, half the users are gone. 
- **Data only** — no editorializing, no spin. Let the records speak. Every published fact links back to its official source.
- **Plain English** — no legal, legislative, or bureaucratic jargon anywhere in the UI.
- **Mobile-first** — most users will discover and use this on their phone.
- **Open methodology** — how data is sourced, normalized, and displayed is documented publicly so it cannot be credibly called biased.
- **All three branches** — Legislative, Executive, and Judicial are treated as equal pillars of the product.

## Scope

| Branch | What it covers | Update cadence |
| --- | --- | --- |
| Legislative | 535 members of Congress, bills, votes, committees, campaign finance, lobbying | Every 30 min in session, daily otherwise |
| Executive | President, VP, Cabinet, 15 departments, agency heads, executive orders | Weekly sync + daily Federal Register feed |
| Judicial | 9 SCOTUS justices, 179 circuit judges, 677 district judges, opinions | As opinions are published |

State and local layers (state legislatures, governors, city councils, state courts) extend the same model once the federal build is stable. Full source list, cadences, and JSON output contracts are in [CODE-MANIFEST.md](CODE-MANIFEST.md).

The product's signature feature is the **full bill pipeline**: a single timeline connecting a bill's introduction (Congress.gov) through signature or veto (Federal Register) through any judicial challenge (CourtListener). No other civic tool currently connects all three stages in one view.

## Where things stand right now

The project is deliberately being proven on the **federal legislative slice** before it's widened: members, bills, votes, committees, campaign finance and ZIP-to-district lookup, backed by Postgres and source-specific refresh jobs. Production moved to a self-hosted deployment platform on 2026-11-09. Reliability, recovery and environment isolation take priority over expanding the product.

Two things are intentionally **on hold**, not forgotten:

- **LLM/plain-English summarization** — the AI/LLM feature set (bill summaries, EO summaries, opinion summaries, natural-language search) is deferred. GovMap ships with raw, sourced data only until there's a human review process that can actually keep pace with it. See [AGENTS.md](AGENTS.md) for the current boundary.
- **Caching (Redis)** — not wired in yet. It gets added when an endpoint actually needs it, not before.

## Data approach

Every pipeline follows the same three-layer contract:

1. **Source pipeline** — one script per source, isolated. Pull, handle that source's auth/pagination/rate limits, validate shape and write raw staging JSON. Refresh orchestration records the outcome in the Postgres `pipeline_status` table.
2. **Normalization** — map raw fields to the canonical schema, resolve cross-source IDs (Bioguide ID for federal legislative people, OCD ID for state/local, FIPS for geography, CGAC for agencies), enforce ISO 8601 on every date, write to Postgres.
3. **JSON output** — a database query serialized to the canonical output file/endpoint, consumed by the frontend.

Nothing skips a layer. The full identifier and normalization rules are non-negotiable and documented in [AGENTS.md](AGENTS.md).

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 3, Node.js 24 |
| Pipelines | Python scripts, one per source, scheduled via APScheduler |
| Infrastructure | Self-hosted deployment platform; Docker Compose resources reached through Cloudflare Tunnel (`cloudflared`), no application host ports; GitHub Actions for CI, manual deployment |

Self-hosting is the current low-cost deployment choice. Application containers and persistent data are managed by the deployment platform; backups must also exist outside that server.

## Sites & branding

GovMap serves the marketing site and platform on one host:

- **govmap.us** — the marketing site (`frontend/app/page.tsx`): what GovMap is, why it exists, and a way in.
- **govmap.us/congress** — the platform entry point, with members, bills and votes on the same host.
- **dev.govmap.us** — the separate test environment, protected by Cloudflare Access and seeded from a production snapshot.

Navigation uses relative paths defined in `frontend/lib/site-config.ts`. Separate `app.govmap.us` and `api.govmap.us` hosts are not part of the current deployment. Browser `/api/*` requests are forwarded by Next.js to the private backend.

Brand assets live in `frontend/public/` (`logo-dark.png`, `logo-light.png` — full lockups with an opaque background baked in, meant for full-bleed placement, not floating over an arbitrary background color). The favicon (`frontend/app/icon.png`) is a square crop of just the Capitol mark from the dark logo, generated because no standalone icon-only asset existed yet — a proper source mark would give a cleaner result and is a fine thing to swap in later.

**Open:** `siteConfig.socialLinks` and `contactEmail` are intentionally empty — nothing fake is linked until real accounts exist. `supportLinks` holds the six live donation platforms shown on the landing page; the landing page also carries a "seeking a fiscal sponsor" note.

## Local development

Prerequisites: Python 3.13, Node.js 24, and Docker (for local Postgres — or point `DATABASE_URL` at any Postgres 16 instance).

```bash
# 1. Start Postgres
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.pipelines.congress_legislators   # pull + validate + stage
python -m app.normalize.members                # normalize + load into Postgres
uvicorn app.main:app --reload                  # http://localhost:8000

# 3. Frontend (separate terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev                                    # http://localhost:3000
```

Visit `http://localhost:3000/members` — it should list current members of Congress, pulled from the `unitedstates/congress-legislators` GitHub repo, normalized, and served through the API. Marketing and platform routes use the same local host, just as they do in production.

## Production deployment

### Security-update validation

The production cutover used `e1e082a`, including the committed frontend
lockfile and the Next.js 16 / Node.js 24 upgrade.
[CI run 42605361712](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42605361712)
passed for that exact commit, including backend lint/tests, frontend lint,
route type generation, TypeScript checking, the production build and the
dependency audit. The frontend installs with `npm ci`.

On 2026-11-09, the scheduler-switch changes were merged to `main` as
`118e1ab3fbd01451b5574cc406f8948f813c151c`.
[CI run 42704119369](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42704119369)
passed for that merge commit. The operator reported deploying the merged
branch to production; confirm the SHA in the deployment log matches the
CI-tested commit before relying on that release identity.

For subsequent releases, develop and validate on `dev` before promotion to
`main`. Check CI for both the tested development commit and the resulting
production commit: a merge can give `main` a different SHA. The **Lint**
workflow audits development dependencies as well as runtime dependencies;
any vulnerability or audit-service error fails CI.
Fix findings rather than using `npm audit fix --force` or ignoring exit codes.
The **Frontend lockfile** workflow and `frontend-security-<commit SHA>`
artifacts support deliberate lockfile updates; commit the reviewed lockfile
and rerun CI before deploying it.

Backend dependencies follow the same rule:
1. Edit the top-level pins in `backend/requirements.in`, never
   `requirements.txt` directly.
2. The Lint workflow's `backend-audit` job recompiles the hash-locked install
   set on Linux/Python 3.13, keeping the committed pins, and uploads it as
   `backend-lock-<commit SHA>`. It warns when that differs from the committed
   lock.
3. Review that file, commit it as `backend/requirements.txt`, and rerun CI.

The image installs with `--require-hashes`, so a package or hash missing from
the lock fails the build. The same workflow audits the lock exactly as
committed and fails on any `pip-audit` finding and on any fixable high or
critical vulnerability in the built images. Base images are pinned by digest
and Actions by commit SHA. Dependabot opens weekly grouped bump PRs against
`dev`.

ESLint 9 is retained for the current React/import plugins' declared peer
compatibility. It is end-of-life; the deprecation warning remains a tooling
support limitation, not evidence that the dependency audit passed.

The legacy GitHub Deploy workflow is disabled; keep it disabled, keep
auto-deploy off, and use manual deployments. Its file is also retired in code:
it no longer triggers on push, accepts only a manual dispatch and has
read-only repository permissions, so re-enabling it by mistake cannot
auto-deploy. Deployment is not yet
automatically gated on CI; require passing checks for the release SHA,
recoverable off-server backups and an explicit manual deployment.

### Deployment topology and configuration

The deployment uses [docker-compose.PaaS.yml](docker-compose.PaaS.yml), with
five services: `postgres`, `backend`, `frontend`, `cloudflared` and `backup`
(idle unless `BACKUP_ENABLED=true`; see the
[backup service guide](docs/backup-service.md)). For a
revision containing this renamed file, update each resource's repository
Compose path after that revision is available on its branch and before a
manual deployment. A running resource is not changed by the repository rename.

| Environment | Git branch | Public hostname | Cloudflare tunnel | Current state |
| --- | --- | --- | --- | --- |
| Production | `main` | `govmap.us` | `govmap-prod` | Live and checked |
| Test | `dev` | `dev.govmap.us` | `govmap-dev` | Snapshot restored; Access and application checks passed |

Each environment must have its own deployment resource, private Compose
network, Postgres volume, log volume, database password and tunnel token.
Do not share production volumes or service-name aliases with the test
environment. Container names change on redeploy; identify the current
resource's containers before running operational commands.

- Leave the resource's **Domains** fields empty for this tunnel-only setup.
- Publish only the frontend: the tunnel's public application route points
  to **HTTP `frontend:3000`**, with no path restriction. Do not publish
  Postgres or add a separate backend hostname.
- The proxied DNS CNAME for each hostname must target that environment's
  **current Tunnel ID** followed by `.cfargotunnel.com`. A new route can
  leave a pre-existing DNS record pointing at a deleted tunnel, causing
  error 1033 even while the new connector is healthy. Check both the route
  and DNS target after any tunnel replacement.
- Use one connector per tunnel for this single-instance deployment. Never
  reuse the production tunnel token for test; that creates a production
  replica rather than a separate environment.

Set variables on the appropriate deployment resource, not in shared
project/team configuration that could also affect production:

| Variable | Production | Test |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Production-only secret | Separate secret; preserve the password if retaining an existing database |
| `CLOUDFLARE_TUNNEL_TOKEN` | `govmap-prod` token | `govmap-dev` token |
| `NEXT_PUBLIC_API_URL` (build) | `http://backend:8000` | `http://backend:8000` |
| `NEXT_PUBLIC_APP_URL` (build) | `https://govmap.us` | `https://dev.govmap.us` |
| `NEXT_PUBLIC_MARKETING_URL` (build) | `https://govmap.us` | `https://dev.govmap.us` |
| `CORS_ORIGINS` | `https://govmap.us` | `https://dev.govmap.us` |
| `SCHEDULER_ENABLED` (runtime, worker) | `true` (default) | `false` for the approved snapshot-only setup |
| `API_*` / `WORKER_*` `_REQUESTS_PER_HOUR` (runtime) | Defaults (see below) | Defaults; separate source keys keep test off production quotas |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (build) / `TURNSTILE_SECRET_KEY` (runtime) | Paired production widget keys | Separate paired test widget keys, or both empty behind restricted test access |
| `API_DOCS_ENABLED` (runtime) | `false` (default) | `false`; enable only temporarily for schema inspection, then redeploy with it off |
| `CONGRESS_GOV_API_KEY`, `FEC_API_KEY`, `HUD_API_TOKEN` | Production credentials | Separate credentials if running keyed refreshes; do not compete for production API quotas |

Build variables require a frontend rebuild, not just a container restart.
`NEXT_PUBLIC_API_URL` is used by the build-time API rewrite; do not set it to
the public frontend hostname, which would proxy requests back to themselves.
The frontend also has `API_INTERNAL_URL=http://backend:8000` at runtime.
Keep `INTERNAL_USER` and `INTERNAL_PASSWORD` empty unless deliberately
configuring authenticated internal operations.

The backend runs Alembic migrations before serving. Scheduled refreshes run in
the separate `worker` service from the same image; the backend's own scheduler
is fixed off in the Compose file, so exactly one process schedules refreshes.
`SCHEDULER_ENABLED` controls the worker and defaults to `true`, preserving
production's scheduled refreshes. Set it explicitly to `false` on
snapshot-only test resources: the worker then logs that scheduled refreshes
are disabled and stays idle without connecting to the database. Invalid
boolean values fail settings validation. Missing API keys **do not disable the
scheduler**; keyed jobs record failures and unkeyed jobs can still fetch data.
This switch controls background scheduling only, not CLI refreshes,
request-triggered fetches or application writes.

The worker never migrates. With scheduling enabled, it waits up to five
minutes for the database to reach the Alembic revision built into its image
(the backend applies it), then logs `scheduler started with 8 job(s)`. If the
revision does not arrive, it exits and the restart policy retries; it never
writes to a schema it was not built for. Its health check reads a heartbeat
file touched every 30 seconds, so a blocked event loop turns it unhealthy; a
healthy worker does not mean refreshes succeed, which `source_runs` shows. On
stop it gives refreshes in flight 15 seconds, within a 30-second grace period,
to record their outcome; a cancelled run is recorded as `abandoned`. It gets
the database, source-key, alert and refresh settings, not the API's CORS,
proxy, internal-operations or Turnstile settings. It logs to `worker.log`
beside the API's `app.log` in the `govmap-logs` volume;
`python -m app.logsctl clear-logs` empties both. Its staging JSON lives in the
worker-only `worker-staging` volume, so a redeploy between the 07:00 UTC
members refresh and the 08:00/09:00 sponsored-bill and finance refreshes no
longer leaves them without the legislators file they read. A new volume is
empty until the next members refresh; run
`docker compose exec worker python -m app.pipelines.refresh members` to seed it
sooner.

Run manual refreshes in the worker:
`docker compose exec worker python -m app.pipelines.refresh <source>` (or
`all`). A per-source advisory lock records an overlapping run as `skipped`
rather than loading the same source twice.

PostgreSQL records each outbound attempt in a rolling 60-minute window, before
HTTP starts. The API and worker keep separate shares: `API_*` and `WORKER_*`
prefixed `CONGRESS_REQUESTS_PER_HOUR` (defaults 1000 / 3500),
`FEC_REQUESTS_PER_HOUR` (250 / 650) and `GOVINFO_REQUESTS_PER_HOUR`
(500 / 100). `TOTAL_*` sets the source-wide ceiling (4500 / 900 / 600).
Keep each API/worker pair's sum at or below its total and keep the total
identical across all processes. A process share above the total fails settings
validation. Compose fixes `UPSTREAM_BUDGET_SCOPE` to `api` or `worker`;
manual commands in the worker share the worker allocation, not a new budget.
Do not override that scope or raise limits in a manual command.

Reservations survive restart, failure and cancellation; retries and each
allowed bill-text redirect spend another reservation. JSON API redirects are
refused rather than making uncounted requests. Expired reservations are pruned
on the next admission for that source. Database errors or a missing ledger
fail closed, with an explicit 503/Retry-After for public upstream-dependent
requests; there is no memory-only fallback. Concurrency limits remain local
to each process. This ledger coordinates one database, not multiple deployment
resources: dev and production still need separate source credentials.
The deployment Compose file does not read the unprefixed share variables;
remove any that are still set in the deployment settings.

**First shared-budget rollout (migration 0015):** stop the old API and worker
containers before applying this migration; do not use overlapping/rolling
old and new versions. Old versions do not participate in the ledger.
The migration starts an automatic, one-time **60-minute hold** on Congress,
FEC and GovInfo requests because the old counters cannot be recovered.
Database-backed pages and readiness stay available; features needing a new
upstream request return 503 with Retry-After. Affected refreshes record their
normal error/partial outcome and may alert during the hold. Do not retry them
repeatedly or edit the ledger to bypass it. Afterward, confirm a successful
refresh and a new source-run row before releasing the change to production.
Ordinary redeploys do not restart the hold or clear usage.

The test environment is a **separate deployment resource** seeded from a
production database snapshot, with its own log volume and credentials,
`SCHEDULER_ENABLED=false`, and Cloudflare Access restricting `dev.govmap.us`
to approved identities. The old dev resource remains stopped for recovery.
A production snapshot may contain sensitive operational data; review and
sanitize it as appropriate before allowing wider test access.

The following are safeguards for any future replacement or reseeding. Do not
repeat a restore into the existing environment without verifying backups and
approving the target and data replacement:

1. Prepare the intended `dev` release without rewriting existing history.
   Require green CI on that exact commit before deployment.
2. Verify server capacity before building another stack. Stop the old dev
   resource, but retain its database/log volumes for recovery. Never stop or
   edit production as part of this setup.
3. Configure the Access application and an allow policy before publishing
   the hostname. Do not add a public bypass policy.
4. Create the replacement resource with separate volumes, network, database
   password and the dev tunnel token. Keep auto-deploy off and Domains empty.
   Disable attachment to predefined/shared networks on both resources. Generic
   service aliases such as `postgres`, `backend` and `frontend` must resolve
   only within the intended resource's private network. The stack's own tunnel
   connector does not need a shared deployment-proxy network.
5. With the new test backend stopped, restore a trusted snapshot into the
   new resource's database only. Verify revision and counts before starting
   the test backend. Never restore production logs or environment secrets.
   Record the snapshot timestamp; its copied `pipeline_status` rows describe
   production history, not jobs executed in test.
6. Publish only `dev.govmap.us` through `govmap-dev`, with the old dev
   connector stopped. Verify the DNS tunnel target, Access challenge/denial when
   signed out, authorized browser/API access, an idle worker (scheduled
   refreshes disabled) and absence of test writes/jobs against production.

After a manual deployment, check the internal backend health and
database revision, then the public frontend and `/api/summary`, then that the
worker is healthy and logged its scheduler start (production) or idle message
(test). HTTP 200 on
the frontend does not establish pipeline health. Query `pipeline_status`
for `source`, `status`, `last_run`, `last_success` and `record_count`; do not
publish its raw `detail` field or application logs. Confirm timestamps
advance after the new instance starts. Record counts describe the latest
run, not necessarily the total rows in an entity table.

`pipeline_status` keeps only each source's latest outcome. Every refresh
attempt, including `partial`, `skipped` and `abandoned` ones a later success
would hide, stays in `source_runs` for 400 days. Read it with SQL or, with
`INTERNAL_USER` / `INTERNAL_PASSWORD` configured, `GET /internal/source-runs`
on the private backend: newest first, filtered by `source` and `outcome`,
`limit` up to 500 (default 100), and `before_id` set to the smallest `id` of
the previous page to page back. Its `detail` has credentials removed but is
still operator-only.

### Persistent state and secrets

When diagnosing database authentication, test from a client container against
the intended database's network endpoint. PostgreSQL may trust localhost
connections; a successful localhost login does not then validate a password.
If a shared service alias reaches a different database, correct resource
network isolation before resetting credentials. Use a verified private IP
only as a temporary diagnostic, never as persistent application configuration.

Production secrets are configured on the deployment platform, not committed to the repository.
Keep a protected recovery copy of the environment configuration and required
decryption credentials separately from the server. Restoring environment
variables or reconnecting a tunnel does not restore database or log contents.

Postgres persists in the resource's `postgres-data` volume. API, refresh-worker
and bug-report logs persist in its `govmap-logs` volume and may contain private
information. The worker's latest source snapshots persist in `worker-staging`;
each refresh rewrites them, so they are not backed up. Do not copy production
logs or secrets into a test environment.

Use consistent logical Postgres dumps and separate log archives, keep
off-server copies encrypted, verify transferred checksums, and test restoration
into a named scratch database without replacing the live database. Protect
local plaintext and remove temporary copies and the scratch database after
successful verification.
Keep backup passphrases or private identities separately and recoverably.
`/tank` or another filesystem on the same host is not an off-server backup.

The production `backup` service in the Compose stack creates a private
bundle every 30 minutes (`BACKUP_INTERVAL_MINUTES`) containing a verified
logical database dump and logs. It prepares its
own host directory and needs no shell setup once enabled through the deployment
settings. Deployment configuration and secrets remain in the operator's vault,
not in the bundle. The earlier host timer, script and environment file have
been removed. The operator reports a local copy and two encrypted off-site
destinations. A container bundle retrieved from off-site passed checksum,
required-file and isolated PostgreSQL restore checks on 2026-11-11 UTC, at
revision `0013`. Independent restores from both off-site destinations have
not been recorded. The heartbeat ping and email test notification were
verified; an actual missed-heartbeat alert has not been rehearsed.
Recurring restore checks are tracked in [CODE-MANIFEST.md](CODE-MANIFEST.md).
Keep the old local bundle until replacement copies and earlier-version
retention satisfy the removal gates in the provider-neutral
[backup service guide](docs/backup-service.md), which covers operation and
safe restore rehearsals without private host details.

### Migration and recovery verification: 2026-11-09

- Restored the old VM's final custom-format dump into a separate database
  on the deployment platform and compared revision and table counts before the
  production cutover. The migrated snapshot had revision `0013`, 539 members, 19,489
  bills, 283 votes and 46,012 ZIP-to-district rows.
- Archived the old application and bug-report logs separately and verified
  the transferred archive's checksum; the archive was not merged into the
  live production log volume.
- Recreated `govmap-prod` and corrected the root hostname's stale DNS
  target. The new tunnel was healthy with one connector. The public home
  page and `/api/summary` returned 200; `/health` on the frontend returned
  404. That 404 is a routing check, not by itself proof of network isolation.
- Verified production credentials were present without displaying values.
  The manual HUD refresh succeeded with 46,012 rows. After the pre-promotion
  redeploy, bills recorded `ok` at 13:04 UTC (250 records), votes recorded
  `ok` at 13:01 UTC (200 records), and backfill recorded `ok` at 13:15 UTC.
  All 19,489 bills had a non-null enrichment timestamp, explaining the
  backfill's zero work.
- Created an age-encrypted production backup, decrypted it to a private
  scratch file and restored it into a scratch database. Restore exited
  zero; verified revision `0013`, 539 members, 19,489 bills and 46,012 ZIP
  rows. The operator subsequently confirmed backup safety. Verify
  off-server copy checksums and retain the decryption credentials separately.
- Senate endpoint probes returned 403, while the subsequent application
  refresh recorded `ok`. The blocking cause is unknown; neither observation
  establishes a permanent site-wide access policy or a permanent recovery.
  Future Voteview fallback runs remain degraded (`partial`), with fallback
  attribution and no advance to the official `last_success`.
- Restored a production snapshot into the separate test database and verified
  revision `0013`, 539 members, 19,489 bills and 46,012 ZIP rows before
  starting the test backend. Its scheduler-disabled log appeared, and an
  internal frontend `/api/summary` request returned 200. Signed-out requests
  to the test site and API redirected to Cloudflare Access; the operator
  confirmed authorized access and the displayed data.
- After the subsequent production deployment, the backend started at
  21:42:09 UTC and logged `scheduler started with 8 job(s)` at 21:42:11 UTC.
  `SCHEDULER_ENABLED=true` was present in the running container. Scheduler
  startup alone does not establish that each refresh has completed.
- GitHub reports the legacy Deploy workflow disabled and Lint active. The
  operator reported the old VM shut down and no legacy agents running.

On 2026-11-10, the operator matched production's deployment SHA
`1e6867429226f395c31eaee369ef64314977cee5` to successful
[CI run 42958859237](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42958859237).
The test resource uses the PaaS Compose file with scheduled refreshes and
backups disabled; the retired VM runner was removed from GitHub.
Source, Turnstile and notification credential rotations were confirmed.
Production's database role password and deployment settings were rotated
together, followed by successful TCP authentication, application checks and
a fresh backup-client connection. Dev uses a separate rotated database password.

**Operational follow-ups:** confirm source status and freshness after backend
restarts, including the daily jobs; observe the next scheduled backup
heartbeat; and continue periodic recovery checks. The bundle schedule, off-site
copying, heartbeat ping and test notification have been set up as described above.
A previous `ok` row restored from an older database does
not verify a job on the new server. `partial` is degraded, not an
unconditional success.

Keep the old VM powered off to avoid duplicate jobs, and confirm any other
required workloads before starting or deleting it. Observe production for at
least a week with the VM off, retain it powered off for 30 days before
deletion, and retain independent backups after deleting its disks and
snapshots. Shutdown and deletion are separate operator-approved steps.
Rotate credentials carried over from the old VM without waiting for the
retention period to end; retaining its disks does not require keeping its
credentials valid.

### Legacy VM tooling

[docker-compose.yml](docker-compose.yml) and `scripts/deploy.sh` remain
legacy VM tooling, not the current deployment path. The script syncs
`origin/main`, builds services, runs migrations and refreshes core data with
a bounded timeout. Do not run it on the production server or use it as a
restore shortcut. A production redeploy migrates in the backend and starts
the scheduler in the worker; neither executes that script's deploy-time
refresh. The legacy compose has no worker: its backend still runs the
scheduler in-process; its `shared` budget scope coordinates the backend and
manual commands against the same source-wide totals.

### Credential rotation and Group 0 release gates

Keep production and test credentials separate. Inventory credential names and
whether they were carried over from the old VM; never paste their values into
issues, logs or chat. Rotate one credential at a time, update the protected
vault and the affected deployment settings, and verify its consumer before
revoking the old credential when the provider permits overlap.

- Source keys: `CONGRESS_GOV_API_KEY`, `FEC_API_KEY` and `HUD_API_TOKEN`.
  Verify an authenticated source refresh after redeploy; an older successful
  database status is not evidence that the replacement key works.
- Internal operations: rotate `INTERNAL_USER` / `INTERNAL_PASSWORD` together
  and update authorized operator clients. Leave both unset if unused.
- Turnstile: coordinate the backend secret with the frontend site key and
  rebuild when the site key changes. Verify an actual report submission.
- Tunnel: rotate only the intended environment's token, redeploy its
  connector and verify public routing. Provider rotation may invalidate the
  old token immediately; plan recovery before starting.
- PostgreSQL: updating `POSTGRES_PASSWORD` does not alter the role password
  in an initialized volume. Use a supervised database password change and
  coordinate the backend, backup service and vault. Expect a maintenance
  window; do not delete the volume or put passwords in command arguments.
- Notification and backup credentials: rotate any inherited webhook tokens,
  storage credentials and administrative access separately. Preserve recovery
  access to earlier encrypted backups; do not discard their decryption keys.

Release gates are green CI for the exact promoted commit, that SHA in the
production deployment record, the correct Compose path in both environments,
and `SCHEDULER_ENABLED=false` / `BACKUP_ENABLED=false` in test. The legacy
GitHub Deploy workflow must remain disabled and the retired VM runner must
not accept jobs. Keep the old VM powered off through the 30-day retention
period following the 2026-11-09 cutover (until at least 2026-12-09), then
delete it only with operator approval and independent recovery materials.

### Application health and release identification

The backend's `/health` is a liveness check: it reports whether the API can
respond, even if the database is unavailable. Its `/ready` performs a read-only,
three-second-bounded ORM query against the pipeline status table. It returns
200 only when that query succeeds; missing schema, authentication, connection
and timeout failures return 503 without database details. An empty status table
is valid. Readiness does not certify the contents of every table, source
freshness, scheduler progress, backups or notification delivery.

The public frontend `/health` makes an uncached, five-second-bounded request
to backend readiness. It returns 503 for an unavailable backend, invalid
response or different known frontend/backend commits. Responses contain only
status and build commit identifiers, never database records or credentials.
All health responses use `Cache-Control: no-store`; exclude `/health` from any
custom edge rule that forces caching. Existing `/api/*` routing is unchanged.

Both Compose files define backend and frontend container health checks every
30 seconds, with three failed checks required after a 120-second startup grace
period. These report health to the deployment platform; Docker's
`restart: unless-stopped` does not restart a process merely because its health
check fails. No auto-healing service is installed. Keep the tunnel route pointed
at the frontend and do not publish the backend or database to monitor them.

Images record `SOURCE_COMMIT` at build time as `APP_COMMIT_SHA`. Enable the
deployment platform's source-commit availability during builds for both
environments, then rebuild. Do not enter a fixed SHA that becomes stale on
the next deployment. A build with no supplied commit reports `null`, not a
fabricated release identifier; it may still be ready. For manual Compose
builds, supply `SOURCE_COMMIT` as the exact full Git SHA being built.
Compare both identifiers in `https://govmap.us/health` with the successful
deployment and CI commit. The stamp is deployment evidence, not cryptographic
image attestation.

Deploy to test first with scheduled refreshes and backups disabled. Confirm
frontend and backend containers become healthy, `/health` returns 200 with
matching commit identifiers, and normal data pages still work. In isolated
test only, stop the backend in the deployment UI and confirm the frontend
health route returns 503; restore it and require recovery to 200. Do not
interrupt production to rehearse failures. Test site access controls still
apply to `/health`. Promote only after CI and test checks pass; after promotion
repeat the healthy checks in production. Roll back by deploying the previous
CI-tested commit; these changes need no schema migration.

Group 1's additional external uptime service, stale-pipeline alerts, webhook
work and disk-space thresholds are explicitly on hold at the operator's
request. The existing backup heartbeat remains in use; application health
checks neither send its ping nor establish backup success.

### Request, browser and disclosure hardening

- **Browser headers.** Every frontend response sends `nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`
  with `Content-Security-Policy: frame-ancestors 'none'`, a
  `Permissions-Policy` denying camera, microphone, geolocation, payment and
  USB, and one-year HSTS without `includeSubDomains` or `preload` (those bind
  every subdomain and need a separate decision). `X-Powered-By` is not sent.
  A script/style CSP is deferred: it needs per-request nonces plus Turnstile
  allowances. If a Cloudflare rule also sets these headers, keep the values
  identical rather than sending conflicting duplicates.
- **API schema.** `/docs`, `/redoc` and `/openapi.json` are off unless
  `API_DOCS_ENABLED=true`. Internal routes are never listed in the schema and
  require `INTERNAL_USER` / `INTERNAL_PASSWORD`; with either unset they
  refuse every request.
- **Reports.** With `TURNSTILE_SECRET_KEY` set, a token solved on a hostname
  outside `CORS_ORIGINS` is rejected, so each environment's `CORS_ORIGINS`
  must list its public hostname (already required for report submission).
  Cloudflare's documented dummy test secrets skip only the hostname check.
- **Outbound links and fetches.** Links from source data render only as
  absolute `http(s)` URLs. In-app bill text is fetched only over HTTPS from
  `congress.gov`/`govinfo.gov`, re-checking every redirect, and is truncated
  at 16 MB.
- **security.txt.** [docs/security.txt](docs/security.txt) is prepared for
  publication through Cloudflare at `https://govmap.us/.well-known/security.txt` (Security →
  Settings → Web application exploits → Security.txt). Its reporting link
  needs GitHub private vulnerability reporting enabled, and its email contact
  must be monitored. Verify the public response after publishing. Renew it before its
  `Expires` date; an expired file tells researchers to ignore it.

## Documentation

Core project documents:

- **README.md** (this file) — what GovMap is.
- **[CODE-MANIFEST.md](CODE-MANIFEST.md)** — what's been built, in what order, and what's next.
- **[AGENTS.md](AGENTS.md)** — the rules coding agents (human or AI) follow when working in this repo.
- **[Platform roadmap](docs/platform-roadmap.md)** — proposed engineering and
  source-coverage milestones; planning targets are not deployed capabilities.

## License

GPLv3 — see [LICENSE](LICENSE). GovMap is a nonprofit, nonpartisan civic tool supported by donations and grants, not advertising or political funding.
