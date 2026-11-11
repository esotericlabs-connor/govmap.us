# GovMap.us

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/75e24029-21c9-4501-9e41-4b97de882381" />

<img width="975" height="283" alt="image" src="https://github.com/user-attachments/assets/cb86aa69-3cde-4e54-b2e0-44500704efd0" />


A mobile-first web app that makes the entire US federal government easy to understand for everyday Americans. GovMap presents real, verified, public data — who represents you, how they vote, who runs the agencies that govern you, where the money goes, and how a bill moves from introduction through signing through judicial challenge — in a clean, digestible format, extended to the full process of American government.


> From City Council to Congress.

**Status:** pre-launch. The federal legislative application is running on Coolify at **https://govmap.us**. See [CODE-MANIFEST.md](CODE-MANIFEST.md) for the current build log and phase checklist.

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

The project is deliberately being proven on the **federal legislative slice** before it's widened: members, bills, votes, committees, campaign finance and ZIP-to-district lookup, backed by Postgres and source-specific refresh jobs. Production moved to Coolify on 2026-11-09. Reliability, recovery and environment isolation take priority over expanding the product.

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
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 3, Node.js 24 |
| Pipelines | Python scripts, one per source, scheduled via APScheduler |
| Infrastructure | Self-hosted Coolify server; Docker Compose resources reached through Cloudflare Tunnel (`cloudflared`), no application host ports; GitHub Actions for CI, manual Coolify deployment |

Self-hosting is the current low-cost deployment choice. Application containers and persistent data are managed by Coolify; backups must also exist outside that server.

## Sites & branding

GovMap serves the marketing site and platform on one host:

- **govmap.us** — the marketing site (`frontend/app/page.tsx`): what GovMap is, why it exists, and a way in.
- **govmap.us/congress** — the platform entry point, with members, bills and votes on the same host.
- **dev.govmap.us** — the separate test environment, protected by Cloudflare Access and seeded from a production snapshot.

Navigation uses relative paths defined in `frontend/lib/site-config.ts`. Separate `app.govmap.us` and `api.govmap.us` hosts are not part of the current deployment. Browser `/api/*` requests are forwarded by Next.js to the private backend.

Brand assets live in `frontend/public/` (`logo-dark.png`, `logo-light.png` — full lockups with an opaque background baked in, meant for full-bleed placement, not floating over an arbitrary background color). The favicon (`frontend/app/icon.png`) is a square crop of just the Capitol mark from the dark logo, generated because no standalone icon-only asset existed yet — a proper source mark would give a cleaner result and is a fine thing to swap in later.

**Open:** `siteConfig.socialLinks` and `contactEmail` are intentionally empty — nothing fake is linked until real accounts exist. `supportLinks` holds the six live donation platforms shown on the landing page; the landing page also carries a "seeking a fiscal sponsor" note.

## Local development

Prerequisites: Python 3.11+, Node.js 24, and Docker (for local Postgres — or point `DATABASE_URL` at any Postgres 16 instance).

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
branch to production; confirm the SHA in Coolify's deployment log matches the
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

ESLint 9 is retained for the current React/import plugins' declared peer
compatibility. It is end-of-life; the deprecation warning remains a tooling
support limitation, not evidence that the dependency audit passed.

The legacy GitHub Deploy workflow is disabled; keep it disabled, keep Coolify
auto-deploy off, and use manual deployments. Deployment is not yet
automatically gated on CI; require passing checks for the release SHA,
recoverable off-server backups and an explicit manual deployment.

### Coolify topology and configuration

Coolify uses [docker-compose.coolify.yml](docker-compose.coolify.yml), with
four services: `postgres`, `backend`, `frontend` and `cloudflared`.

| Environment | Git branch | Public hostname | Cloudflare tunnel | Current state |
| --- | --- | --- | --- | --- |
| Production | `main` | `govmap.us` | `govmap-prod` | Live and checked |
| Test | `dev` | `dev.govmap.us` | `govmap-dev` | Snapshot restored; Access and application checks passed |

Each environment must have its own Coolify resource, private Compose
network, Postgres volume, log volume, database password and tunnel token.
Do not share production volumes or service-name aliases with the test
environment. Coolify container names change on redeploy; identify the current
resource's containers before running operational commands.

- Leave Coolify's **Domains** fields empty for this tunnel-only setup.
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

Set variables on the appropriate Coolify resource, not in shared
project/team configuration that could also affect production:

| Variable | Production | Test |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Production-only secret | Separate secret; preserve the password if retaining an existing database |
| `CLOUDFLARE_TUNNEL_TOKEN` | `govmap-prod` token | `govmap-dev` token |
| `NEXT_PUBLIC_API_URL` (build) | `http://backend:8000` | `http://backend:8000` |
| `NEXT_PUBLIC_APP_URL` (build) | `https://govmap.us` | `https://dev.govmap.us` |
| `NEXT_PUBLIC_MARKETING_URL` (build) | `https://govmap.us` | `https://dev.govmap.us` |
| `CORS_ORIGINS` | `https://govmap.us` | `https://dev.govmap.us` |
| `SCHEDULER_ENABLED` (runtime) | `true` (default) | `false` for the approved snapshot-only setup |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (build) / `TURNSTILE_SECRET_KEY` (runtime) | Paired production widget keys | Separate paired test widget keys, or both empty behind restricted test access |
| `CONGRESS_GOV_API_KEY`, `FEC_API_KEY`, `HUD_API_TOKEN` | Production credentials | Separate credentials if running keyed refreshes; do not compete for production API quotas |

Build variables require a frontend rebuild, not just a container restart.
`NEXT_PUBLIC_API_URL` is used by the build-time API rewrite; do not set it to
the public frontend hostname, which would proxy requests back to themselves.
The frontend also has `API_INTERNAL_URL=http://backend:8000` at runtime.
Keep `INTERNAL_USER` and `INTERNAL_PASSWORD` empty unless deliberately
configuring authenticated internal operations.

The backend runs Alembic migrations before serving. `SCHEDULER_ENABLED`
defaults to `true`, preserving production's scheduled refreshes. Set it
explicitly to `false` on snapshot-only test resources before starting the
backend; startup logs that scheduled refreshes are disabled. Invalid boolean
values fail settings validation. Missing API keys **do not disable the
scheduler**; keyed jobs record failures and unkeyed jobs can still fetch data.
This switch controls background scheduling only, not CLI refreshes,
request-triggered fetches or application writes.

The test environment is a **separate Coolify resource** seeded from a
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
5. With the new test backend stopped, restore a trusted snapshot into the
   new resource's database only. Verify revision and counts before starting
   the test backend. Never restore production logs or environment secrets.
   Record the snapshot timestamp; its copied `pipeline_status` rows describe
   production history, not jobs executed in test.
6. Publish only `dev.govmap.us` through `govmap-dev`, with the old dev
   connector stopped. Verify the DNS tunnel target, Access challenge/denial when
   signed out, authorized browser/API access, scheduler-disabled startup
   and absence of test writes/jobs against production.

After a manual Coolify deployment, check the internal backend health and
database revision, then the public frontend and `/api/summary`. HTTP 200 on
the frontend does not establish pipeline health. Query `pipeline_status`
for `source`, `status`, `last_run`, `last_success` and `record_count`; do not
publish its raw `detail` field or application logs. Confirm timestamps
advance after the new instance starts. Record counts describe the latest
run, not necessarily the total rows in an entity table.

### Persistent state and secrets

Production secrets are configured in Coolify, not committed to the repository.
Keep a protected recovery copy of the environment configuration and required
decryption credentials separately from the server. Restoring environment
variables or reconnecting a tunnel does not restore database or log contents.

Postgres persists in the resource's `postgres-data` volume. Application and
bug-report logs persist in its `govmap-logs` volume and may contain private
information. Do not copy production logs or secrets into a test environment.

Use encrypted logical Postgres dumps and separate log archives, keep copies
off-server, verify transferred checksums, and test restoration into a named
scratch database without replacing the live database. Remove decrypted
scratch dumps and the scratch database after successful verification.
Keep backup passphrases or private identities separately and recoverably.
`/tank` or another filesystem on the same host is not an off-server backup.

[Backups and recovery](docs/backups-and-recovery.md) describes the production
backup. A systemd timer on the Coolify server writes one verified, root-only
bundle every night. The bundle holds the database dump, logs and Coolify
deployment configuration. Duplicati copies it, encrypted, to two off-server
destinations. On 2026-11-10 the bundle was restored into a scratch database
and matched production. A missed-backup alert, a restore from a Duplicati
copy, and a monthly restore check are tracked in
[CODE-MANIFEST.md](CODE-MANIFEST.md). A database dump alone does not recreate
the deployment; the runbook lists what else recovery needs.

### Migration and recovery verification: 2026-11-09

- Restored the old VM's final custom-format dump into a separate database
  on Coolify and compared revision and table counts before the production
  cutover. The migrated snapshot had revision `0013`, 539 members, 19,489
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

**Still pending:** verify the actual production deployment SHA against its CI
run; confirm source status and freshness after the latest backend start,
including the daily jobs; and configure and rehearse scheduled off-server
backups and alerting. A previous `ok` row restored from an older database does
not verify a job on the new server. `partial` is degraded, not an
unconditional success.

Keep the old VM powered off to avoid duplicate jobs, and confirm any other
required workloads before starting or deleting it. Observe production for at
least a week with the VM off, retain it powered off for 30 days before
deletion, and retain independent backups after deleting its disks and
snapshots. Shutdown and deletion are separate operator-approved steps.

### Legacy VM tooling

[docker-compose.yml](docker-compose.yml) and `scripts/deploy.sh` remain
legacy VM tooling, not the Coolify deployment path. The script syncs
`origin/main`, builds services, runs migrations and refreshes core data with
a bounded timeout. Do not run it on the Coolify server or use it as a
restore shortcut. A Coolify backend restart runs migrations and starts the
scheduler; it does not execute that script's deploy-time refresh.

## Documentation

Only three documents explain and govern this project:

- **README.md** (this file) — what GovMap is.
- **[CODE-MANIFEST.md](CODE-MANIFEST.md)** — what's been built, in what order, and what's next.
- **[AGENTS.md](AGENTS.md)** — the rules coding agents (human or AI) follow when working in this repo.

## License

GPLv3 — see [LICENSE](LICENSE). GovMap is a nonprofit, nonpartisan civic tool supported by donations and grants, not advertising or political funding.
