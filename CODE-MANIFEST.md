# CODE-MANIFEST.md

What's been built, in what order, and what's next. This is a living log — add an entry every time a meaningful piece of the build lands. For what GovMap is, see [README.md](README.md). For how it gets built, see [AGENTS.md](AGENTS.md).

## Build log

**2026-11-09 — Coolify-aware encrypted database backup utility (validation pending)**
Added `scripts/backup-coolify-database.sh` for an explicitly selected
production resource. It requires exactly one running matching Postgres
container, verifies readiness, streams a custom-format `pg_dump` through `age`,
and publishes the complete encrypted result without replacing prior files.
It does not back up the raw live Postgres volume and does not install a timer
or change production. Synthetic failure-path tests were added for missing or
ambiguous containers, readiness, dump and encryption failures. No local tests
were run; the script has not been executed against Coolify. Require CI on the
exact `dev` commit and a supervised backup plus isolated restore rehearsal
before configuring Duplicati or a schedule. See
[backups and recovery](docs/backups-and-recovery.md).

**2026-11-09 — Coolify test verification and scheduler-enabled release**
The replacement `dev` resource restored a production snapshot into its own
database: revision `0013`, 539 members, 19,489 bills and 46,012 ZIP rows.
The test backend logged scheduled refreshes disabled, and an internal
frontend `/api/summary` check returned 200. Signed-out site and API requests
redirected to Cloudflare Access; the operator confirmed authorized access
and displayed data. The old dev resource remains stopped.

The scheduler-switch changes were merged to `main` as
`118e1ab3fbd01451b5574cc406f8948f813c151c`, which passed
[CI run 42704119369](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42704119369).
The operator reported deploying the merged branch to production; the actual
Coolify deployment SHA still needs to be matched to the CI-tested commit.
After that deployment, the production backend showed `SCHEDULER_ENABLED=true`
and logged eight scheduled jobs immediately after startup. This verifies
registration, not subsequent job completion.

GitHub reports the legacy Deploy workflow disabled and Lint active. The
operator reported the old VM powered off and no legacy agents running.
Post-deployment source freshness, automated off-server backups, recurring
restore rehearsals and alert delivery remain to be verified. See the
[README deployment record](README.md#production-deployment).
The selected backup direction is a daily consistent database backup in a
dedicated server directory, copied with application recovery materials by
Duplicati to two off-server destinations. It is not yet configured or tested.

**2026-11-09 — Isolated snapshot test setup (initial preparation checkpoint)**
The approved replacement test environment is a fresh Coolify resource with
a production database snapshot, independent volumes/network/credentials,
scheduled refreshes off, and Cloudflare Access on `dev.govmap.us`. Preserve
the old dev resource stopped for recovery; do not delete its data or branch
history. `SCHEDULER_ENABLED` now defaults to `true` and is passed through both
Compose files; setting it to `false` skips scheduler startup and shutdown
and logs the disabled state. It does not disable manual refreshes or
request-triggered fetches. Regression tests cover the default, environment
parsing, invalid input and both lifespan modes, including exceptional exit.
No tests were run locally; this checkpoint required green CI on the exact
test release before deployment. Production had not yet been redeployed at
this point; the later verification is recorded above.

**2026-11-09 — Coolify production cutover and recovery verification**
Production is live at `https://govmap.us` on the `main` Coolify resource,
using the environment's own `govmap-prod` tunnel and private backend/Postgres.
The final old-VM database was restored and checked before cutover. A fresh
encrypted production backup subsequently passed a scratch-database restore:
revision `0013`, 539 members, 19,489 bills and 46,012 ZIP-to-district rows.
The operator confirmed backup safety; transferred-copy checksums and
recoverable decryption credentials remain operational requirements.
Post-redeploy bills, votes, backfill and manual HUD refreshes recorded `ok`;
zero unenriched bills explain backfill's zero work. At that checkpoint,
daily-source checks, isolated test-environment verification, automated backups
and old-VM retirement remained pending, and the old backend was stopped. See the
[README deployment record](README.md#production-deployment) for topology,
configuration, recovery evidence and the remaining retirement gates.

**2026-11-09 — Production readiness: audit fix, lint fix, Coolify Compose (lockfile validated)**
CI on `4e30c04` (the push of the 2026-11-08 work) passed backend lint and
tests but failed frontend lint and the audit gate; build/typecheck were skipped.
- Audit: 8 moderate findings, all one advisory
  ([GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249),
  minimatch globparts DoS) reached via
  `@typescript-eslint/typescript-estree@8.72.1` → `minimatch@10.2.6`
  (lint tooling, dev-only). npm's suggested fix was a downgrade to
  `eslint-config-next@15`, which was rejected. A scoped `overrides` entry pins
  only that consumer's `minimatch` to 11.0.5 (patched); other ESLint packages keep
  their separate `minimatch@3`. This is a major-version bump for that consumer,
  so passing lint in CI is the compatibility evidence. Remove the
  override once typescript-eslint depends on a patched release.
- Lint: `app/account/page.tsx` used `<a href="/">` for internal navigation;
  now `next/link`. The follow-up run (`d0932b5`) passed the audit gate and
  still failed on another error:
  `components/UsMap.tsx` wrote `zoomRef.current` during render
  (`react-hooks/refs`). It's now synced in a `useLayoutEffect` keyed on
  `zoom`; the ref is only read by event handlers and effects, which run
  after that sync, so tween start points are unchanged. The remaining
  `set-state-in-effect` items are warnings by design (see 2026-11-08).
- `docker-compose.coolify.yml` (previously only on `dev`) added to `main` for
  the Coolify production resource. Root-only topology: only the frontend is
  published, through that environment's own tunnel. `NEXT_PUBLIC_API_URL`
  defaults to `http://backend:8000`, so the build-time `/api/*` rewrite
  targets the private backend instead of the retired `api.govmap.us`. CORS
  defaults to `https://govmap.us`. Each environment (dev/production) is a
  separate Coolify resource with its own database, volumes and tunnel token.
- CI on `bc5c4c2` passed backend lint/tests, frontend lint, Next type generation,
  TypeScript checking, the production build and the dependency audit
  ([run 42603854918](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42603854918)).
  Its generated lockfile matches the frontend manifest and resolves the scoped
  minimatch override to 11.0.5; all 448 packages resolve from
  `registry.npmjs.org`.
- `frontend/package-lock.json` is now committed from that run's CI artifact
  (byte-identical, so integrity hashes are unchanged). The Dockerfile's
  `npm ci` requires it. CI on `e1e082a` subsequently passed with the committed
  lockfile, including the `npm ci` install, lint/tests, typecheck, production
  build and audit
  ([run 42605361712](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42605361712)).

**2026-11-08 — Vote source repair and frontend platform upgrade (CI pending)**
The first deploy after the refresh bounds (`8630cad`) finished on time, but the
refresh was unhealthy: bills `partial`, and votes failed in both chambers.

Bills: Congress.gov read timeouts tripped the new outage breaker as designed
(9 staged, 6 failed, 235 not attempted, recorded `partial`). The cause is still
unknown; no code change in this entry.

House votes: the observed missing `roll999.xml` request returned
`<xml>Error sanitizing file "roll999.xml"…</xml>` rather than a roll-call
document. The production probes treated it as HTTP success. `_exists` only checked the
status code, so the max-roll binary search settled on 999 and every fetched
roll parsed to nothing ("no house votes parsed (year 2026, top roll 999)").
`_exists` now streams the first 1 KB and requires a `<rollcall-vote` root.
Only a definite missing-file response counts as absence. Timeouts, blocks,
and unexpected responses at any probe raise instead of silently truncating
the discovered range. A failed/mismatched detail prevents publication of
the batch, preserving the previous staging.

Senate votes: the production menu request returned HTTP 403, also reproduced
by a read-only fetch. This establishes refusal of those requests, not a
site-wide policy against every non-browser client. The blocking rule and its
cause are unknown. Changes:
- `senate_lis_votes` now fails with a clear error on a non-200, unparseable or
  non-`vote_summary` menu, invalid menu entries, or any failed/mismatched
  selected detail. A partially successful official pull also triggers fallback.
- `refresh_votes` falls back to a new `voteview_senate_votes` pipeline only when
  the official pull raises. Source:
  [Voteview](https://voteview.com/) (Lewis, Poole, Rosenthal, Boche, Rudkin,
  Sonnet, *Voteview: Congressional Roll-Call Votes Database*), per-Congress
  `S{c}_rollcalls/members/votes.csv`.
- Voteview carries Bioguide IDs, so positions join `members` directly.
  `clerk_rollnumber` is the official Senate vote number, so vote IDs
  (`s{congress}-{session}-{roll}`) are the same as LIS IDs. A later official
  pull overwrites the same rows.
- `source_url` points to the Voteview votes dataset; attribution persists
  through the existing database/API field without a migration. The vote page
  labels it "Voteview Data", not "Official Record", and discloses the fallback.
  Each staged vote also carries `provenance: "voteview"`.
- Cast codes: paired and announced votes (2–5) and 9 stage as Not Voting,
  matching the official tally. 0 (not a member) is skipped. Totals are
  recomputed from positions. Malformed CSV, conflicting identifiers, duplicate
  member positions, unknown cast codes, missing Bioguide mappings, missing
  positions, and inconsistent tallies reject the batch before publication.
  No name-based identity matching is attempted.
- Fallback runs record `partial`, never advance the official `last_success`,
  and do not produce an all-sources-ok CLI result. Voteview explicitly excludes
  quorum calls and vacated votes; its freshness relative to the official feed
  is unverified. A cached download is not evidence of fresh government data.
- The normalizer reads only chambers that succeeded in the current refresh;
  failed chambers' old staging is not replayed. Degraded/failed vote sources
  are not retried as a whole batch by the deploy refresh runner.
- The CSVs are re-downloaded at most every `VOTEVIEW_MIN_REFETCH_HOURS`
  (default 6), because the scheduler runs votes every 30 minutes.
- Staging reuse validates the complete payload, identifiers and totals.
  Publication uses a unique temporary file followed by atomic replacement.

Frontend platform: the attached CI install reported 11 vulnerabilities
(1 critical, 4 high, 6 moderate), without a detailed dependency-tree report.
The [Image Optimizer advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
includes the previous Next 14.2.35 version; `images.unoptimized` limits exposure
to that path but does not remediate other advisories. The
[November security release](https://nextjs.org/blog/november-2026-security-release)
identifies Next 16.4.5 as patched. Published package versions/peer metadata
were checked, not installed or audited locally. Node 20 reached end-of-life
on 2026-04-30; the approved runtime is Node 24.

Versions:

| Package | From | To |
| --- | --- | --- |
| `next`, `eslint-config-next` | 14.2.35 | 16.4.5 (November 2026 security release) |
| `react`, `react-dom` | 18.3.1 | 19.3.1 |
| `eslint` | 8.57.0 | 9.39.5 |
| `postcss` | 8.4.39 | 8.5.32 |
| `typescript` | 5.5.3 | 5.9.3 |

`tailwindcss` (3.x), `autoprefixer` and `@types/*` also moved to current
releases.

Code and config changes:
- The six dynamic pages await `params`/`searchParams`, which Next 16 requires.
- `<html>` gets `data-scroll-behavior="smooth"`, which keeps the instant
  scroll-to-top on navigation.
- `next lint` (removed in Next 16) is replaced by `eslint .` with
  `frontend/eslint.config.mjs`.
- Node 24 in the Dockerfile, CI and the README.

CI (`lint.yml`):
- read-only token
- full `npm audit` gate, including development dependencies and lower
  severities; audit errors are not ignored
- route type generation, TypeScript checking and a `next build` gate
- SHA-labeled lockfile and audit-report artifacts, retained even on failure

The manual `Frontend lockfile` workflow resolves and validates a lockfile.
The `dev` Lint job also supplies the artifact before manual dispatch is
available on the default branch. The Dockerfile now requires the committed
lockfile and uses `npm ci`; there is no production install fallback.

Regression cases are in `backend/tests/test_vote_pipelines.py`. Nothing in this
entry has been run on this static checkout. Added an orchestration-to-normalizer
test with real pipeline/normalizer logic and fake HTTP/DB I/O, covering the
Senate 403 fallback, source attribution and exclusion of failed-chamber staging.
This is not a real database integration test. The latest inspected GitHub CI
still tested `8630cad`, not these changes; no green audit/build/vote-test result
is established for this upgrade.

Open:
- Commit the lockfile from the workflow artifact.
- Obtain green CI on the exact locked commit before promotion or Group 1.
- The obsolete `.eslintrc.json` was removed. Only `set-state-in-effect`
  remains a warning for existing effect-driven loading resets; other
  recommended React rules keep their upstream severities.
- ESLint 9.39.5 is also end-of-life. It is retained for the React/import
  plugins' declared ESLint <=9 peer compatibility, not claimed as supported.
  Do not force ESLint 10 past peer requirements.
- Find the Congress.gov timeout cause.
- Watch for senate.gov accepting requests again (the official pull is always tried
  first).

**2026-11-08 — Bounded deploy refresh during Congress.gov outages (CI pending)**
[Deploy run 65](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42450393617)
took 2h12m (earlier deploys took 2–5 min). Congress.gov answered almost every
bill request with a 30s read timeout. The bills loop had no deadline and no
outage stop, so it paid one timeout per bill. It staged 69 of 250 bills and
still recorded `ok`. If every bill had failed, the refresh would have retried
the whole pull up to three times, and the job had no timeout of its own
(GitHub's default is 6h). House and Senate votes failed separately in that run
(no House votes parsed; the Senate menu returned HTTP 403). The deploy only
printed a warning for that.

Fix:
- A Congress.gov timeout or connection failure now raises
  `UpstreamUnavailableError` (`app/services/upstream.py`) at once, without
  retrying.
- `app/pipelines/batch.py` adds `OutageBreaker`, which stops a loop after
  `CONGRESS_MAX_CONSECUTIVE_FAILURES` consecutive outage errors (default 5), and
  `BatchResult`.
- The bills, sponsored-legislation and backfill loops use the breaker. The bills
  pull also has a `CONGRESS_GOV_BILLS_MAX_SECONDS` budget (default 600).
- These pulls stage what they fetched before stopping (safe because they
  upsert), and the refresh records them as `partial`, so `last_success` stays
  honest.
- Committee meetings full-replace their table. They now refuse to stage after a
  failed chamber list, a tripped breaker, or more than 10% failed items. The
  previous code wiped a chamber's meetings when its list call failed.
- `_run_with_retry` no longer retries upstream outages or exhausted request
  budgets.
- Visitor-triggered bill enrichment stays fail-soft.
- `scripts/deploy.sh` caps the deploy refresh at 15m inside the container
  (`GOVMAP_REFRESH_TIMEOUT`). `deploy.yml` sets `timeout-minutes: 30`.

Because the runner executes the copy of `deploy.sh` already on disk, the
in-container cap takes effect on the deploy after the one that ships it. The
job timeout and the pipeline bounds apply immediately. Regression cases are in
`backend/tests/test_upstream_outages.py`; they have not been run on this static
checkout.

Open: the root cause of the timeouts (Congress.gov slowness vs. runner network)
is unknown. The votes loops have no breaker yet, and the Senate 403 and the
House parse failure need their own fix. The bills, backfill and deploy pulls
together approach the 5,000/h Congress.gov key limit, so an incremental
`fromDateTime` bill pull should replace the 250-bill re-pull.

**2026-11-08 — Group 0 baseline and recovery tooling (verification pending)**
GitHub Actions reported successful backend tests/lint and frontend lint/type
checking for commit `f6b0d8f85e981052280349882320b54093c15e7b` in
[Lint run 72](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42450393548);
the [deployment run](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42450393617)
for that trigger also reported success. The deployment script fetches `main`,
so the running SHA is not established by the trigger SHA alone. GitHub's branch
listing reported `main` as unprotected; separate rulesets were not checked.
At that checkpoint, the operator reported that no backups were in place.
Production migration revision, pipeline freshness, and proxy trust were
unverified.

Added inert operator tooling for an age-encrypted GovMap archive, an encrypted
database dump and required Duplicati pre-backup hook, and an empty-target
database restore. The archive includes `.env`, repository files, and the
persistent log volume. At that checkpoint, nothing had been scheduled or
installed, and no backup or restore had been performed. Synthetic regression
cases were added but not run on this static checkout; CI and a real isolated
restore rehearsal are still required. See [backups and recovery](docs/backups-and-recovery.md).
Group 0 remained blocked at that checkpoint until a separate backup and
restore were verified; later recovery evidence is recorded above. Pipeline
status currently lives in PostgreSQL; the JSON reference in
`AGENTS.md` and the earlier Group 3 plan need reconciliation before changing
that contract.

**2026-11-07 — Pre-expansion security guardrails (production verification pending)**
Exact parsed-origin checks replace prefix matching on bug reports. Forwarded
client addresses are ignored unless the socket peer belongs to explicitly
configured trusted proxy CIDRs; Uvicorn proxy rewriting is disabled in the
container. Reports have bounded per-IP and global hourly limits without
clearing active buckets. Shared process-local Congress.gov/OpenFEC/bill-text
request budgets cover retries and refresh jobs, with bounded on-demand worker
admission and explicit HTTP 503 + `Retry-After` on exhaustion. Capacity failures
are not swallowed by enrichment/pipeline fallbacks; optional frontend bill-text
and referral sections show unavailable notices. Donation cache creation rejects
unknown members and invalid cycles. Settings are wired through Compose and the
environment examples; operational limits and proxy prerequisites are documented
in [docs/logs-and-bug-reports.md](docs/logs-and-bug-reports.md).
Regression tests were added for origin spoofing, proxy trust, report quotas,
outbound concurrency/retries, cancellation and capacity responses. Tests,
linters and builds were not run on this static checkout. The later
[Lint run 72](https://github.com/esotericlabs-connor/govmap.us/actions/runs/42450393548)
passed backend tests/lint and frontend lint/type checking for commit
`f6b0d8f85e981052280349882320b54093c15e7b`; it did not establish the running
SHA or verify production ingress configuration.
These changes do not resolve the remaining roster/snapshot/paging integrity
and release-gating findings.

**2026-09-29 — Pre-expansion hardening: Next.js security patch + normalization test harness**
Bug/error cleanup pass before adding new data sources. **Security:** bumped `next` (and `eslint-config-next`) from **14.2.5 → 14.2.35** (`frontend/package.json`) — the latest stable 14.2.x, closing the advisories that affect 14.2.5 including the CVE-2025-29927 middleware auth-bypass, plus SSRF, cache-poisoning, and DoS fixes; no major-version jump, and there's no lockfile + the Dockerfile uses `npm install` (not `npm ci`), so the version bump alone is sufficient. **First tests in the repo:** a pytest harness (`backend/tests/`, `backend/pytest.ini`, `backend/requirements-dev.txt`) covering the pure Layer-2 normalization logic — exactly where AGENTS.md says a silent regression corrupts data. `test_dates` pins the shared ISO-8601 `normalize_date`/`normalize_datetime` (fail-soft, Z-tolerant); `test_member_schema` locks in the term-resilience validator behind the "Vacant / no data" seat bug (drop only malformed terms, keep the sitting member's current seat, reject a wholly-broken record, allow a null-party current term); `test_member_normalize` covers chamber/district mapping, the `served_since` contiguity walk (gap + chamber-switch breaks), party backfill, and the FEC-ids-as-array rule; `test_crosswalk` guards the Bioguide→LIS/FEC/… join backbone; `test_congress_helpers` the D/R/I party bucket. Tests import the pure helpers only (the async engine is connection-lazy, so no Postgres needed to collect/run). Wired into CI as a `backend-tests` job in `.github/workflows/lint.yml` (`pip install -r requirements.txt -r requirements-dev.txt` → `pytest -q`).

**2026-08-18 — Site-wide member blade + in-place donations ledger + same-origin browser API (mobile fixes)**
Three frontend increments that had shipped but weren't logged, plus the mobile-hardening pass that closes them out. **Member profile blade:** every member link across the site now opens a right-side slide-in profile instead of a full navigation (`components/MemberBlade.tsx`, portaled to `<body>` so no ancestor `backdrop-filter` clips a `fixed` panel; provider `lib/member-blade.tsx`). URL sync uses the **History API** (`?member=<id>` push/replace + a `popstate` listener), **not** `router.push`, so opening the blade doesn't re-run the underlying route's server components (no map refetch/blink). `components/MemberLink.tsx` renders a real `<a href="/members/{id}">` (SEO; right/middle/⌘-click fall through to normal nav) but intercepts plain left-click → open blade; wired into every member link (map card, search, ZIP lookup, roster, bill sponsor/cosponsors, committee rosters, vote positions). `components/MemberProfileBody.tsx` is the shared render (`variant: "page" | "blade"`), so the standalone `/members/[bioguide]` page (kept for SEO/deep-links) and the blade share one presentation. **In-place donations ledger:** `components/DonationsLedger.tsx` owns term/sort/offset/data client-side and refetches the list in place — header/search/sort stay mounted, previous rows dim while the next page loads (debounced search, monotonic `reqId` guard against out-of-order responses, fail-soft keeps the last good page), replacing the old keyed-`<Suspense>` that remounted the whole subtree (and the search input) on every keystroke. **Same-origin browser API + mobile fixes:** browser calls to `https://api.govmap.us` failed on mobile (cross-origin request blocked/unreachable from the device; and when the build-time `NEXT_PUBLIC_API_URL` wasn't baked, `publicApiBase` fell back to `localhost:8000` — fine next to a dev backend, dead + mixed-content on a phone) → the map info card read "—", the blade said "couldn't be loaded", and ZIP lookup did nothing. Fix: `publicApiBase` is now `""` (relative `/api/...`) and a `next.config.mjs` `rewrites()` proxies `/api/:path*` to the backend **server-side** (`API_INTERNAL_URL ?? NEXT_PUBLIC_API_URL ?? localhost:8000`); every browser fetch is now same-origin, so the client no longer depends on the `api.` host being reachable/unblocked and CORS drops out of the browser path (SSR via `serverApiBase` unchanged). Also: `FinanceCard` gained a `compact` prop (the blade renders `$2.5M`-style abbreviated topline tiles that were overflowing the 520px blade at the `sm:grid-cols-4` breakpoint; the full page keeps exact figures), and the blade's "Open full page ↗" affordance is now desktop-only (`hidden md:inline`) — on mobile the blade is the whole experience.

**2026-07-26 — Committee meetings (Congress.gov `/committee-meeting`)**
`committee_meetings` table (0012; keyed `(event_id, committee_id)` so a meeting shared by a full committee and its subcommittee shows under both). `congress_committee_meetings.py` pulls the Congress.gov `/committee-meeting` list for the current Congress (full-replace per run — meetings churn and canceled ones drop) → staging; `normalize/committee_meetings.py` upserts. **Surfaced through the existing committee detail endpoint** (`/api/committees/{id}` → `upcoming_meetings` / `recent_meetings`, split by `meeting_datetime` vs now), so no new router — the three-layer contract's API layer is the committees router. Registered in `refresh.py` (`EXTRA_REFRESHERS`) + a scheduler cadence. **0013 (2026-07-26)** widened `event_id`/`meeting_type`/`meeting_status` after a longer-than-`VARCHAR(20)` value raised `StringDataRightTruncationError` and — because the load is a single-transaction full replace — dropped *every* meeting for that run.

**2026-07-24 — On-demand bill enrichment + in-app full text**
`bills.enriched_at` (0011, indexed) distinguishes fully-enriched bills (actions + cosponsors + CRS summary + text link) from the ~17k title-only "index" stubs the sponsored-legislation pipeline creates. `bill_text` caches the full legislative text (reduced to plain text — no `dangerouslySetInnerHTML`) for in-platform rendering. Both are populated at request time by `app/services/bill_enrich.py`: first view of an un-enriched bill triggers a lazy fetch (detail + actions + cosponsors + summary + text), and a **rolling backfill** (`refresh_backfill_bills` in `EXTRA_REFRESHERS`) walks the NULL-`enriched_at` rows to widen coverage past the pull cap toward the full corpus. Fail-soft — a missing key or network error doesn't block the page.

**2026-07-24 — Itemized donations ledger (Increment 4b) + finance Form 3 breakdown**
**Finance breakdown (0009):** widened `member_finance` from the impoverished `/candidates/totals` aggregate to the full `/candidate/{id}/totals` Form 3 line items — combined individual total, the itemized-vs-unitemized (large-vs-small-dollar) split, party money, transfers, self-funding, loans, other receipts, operating expenditures, refunds. `FinanceCard` gained the receipts-source breakdown bar + a grassroots (< $200) vs large-donor split. **Itemized donations (0010):** `contributions` caches individual FEC Schedule A receipts (≥ $200) pulled **on demand** as visitors browse a member's ledger — the full corpus (200k+ rows per big committee) is too large to mirror, so rows are fetched + cached lazily, keyed by the FEC transaction `sub_id`; `donation_fetch` holds the keyset cursor + progress per `(member, cycle)` so paging resumes where it left off. Populated at request time by `app/services/donations.py` (requires `FEC_API_KEY`; fail-soft without it), served by `routers/donations.py` → the `/donations` page + `DonationsLedger`. This is the "named top donors" step flagged as next in Increment 4a — **note it's on-demand, not a mirrored bulk pipeline**, so there's no scheduled refresher; the ledger fills in as members are viewed.

**2026-07-24 — UI redesign pass (Gemini) + Claude finalize**
Second Gemini polish loop ([[gemini-division-of-labor]]) — a full visual system pass: a warm-neutral palette (`slate-warm`), refined `shadow-card`/`-hover`, new keyframes (`slide-down-and-fade`, `ring`), an animated seat-chart with a floating tooltip + ZIP-highlight ring, sticky glassy header with an animated chamber-tab glider (`ChamberTabs`), streaming detail pages (`<Suspense>` + `PageSkeleton`), and restyled hero/cards throughout. **Gemini respected the guardrails**: no backend/`lib/api.ts`/`package.json` edits, no new deps, no external requests (fonts stay build-time `next/font`), server/client boundaries intact, no invented API fields. **Claude finalize pass fixed:** a self-referential CSS var in the cartogram (`--color-govblue: var(--color-govblue)` — it would have invalidated the var that `FinanceCard` relies on) + its now-dead `FILL`/`useEffect`; missing `slate-warm-700/800` shades (used but undefined); a duplicate `DetailKit` import; slimmed `PageSkeleton` so it doesn't nest a second `<main>`/back-link inside detail pages. **Also built the two missing index pages** (`/bills`, `/votes`) that Gemini added to the header nav — server components over the existing `/api/bills` + `/api/votes` list endpoints — and pointed the bill/vote detail back-links at them. Lesson holds: the finalize pass owns reconciling anything Gemini couldn't verify against the running stack.

**2026-07-24 — Bill summaries + full text ("what this bill does")**
Every enriched bill now carries the official **CRS summary** (Congress.gov `/summaries`, HTML stripped to plain text in the normalizer — no `dangerouslySetInnerHTML`) and a link to the latest **full-text version** (`/text`, preferring Formatted Text → PDF → any). Schema 0008 adds `bills.summary`/`summary_date`/`text_url`/`text_version` (distinct from the reserved LLM `summary_plain_english`); `congress_gov_bills` fetches 2 more sub-resources per bill (~5 calls/bill now) and the normalizer keeps the most recent of each. The bill detail page gains a "What this bill does" section (plain-English summary + a "Read the full text ↗" button). Coverage tracks the enriched-bills set (the most-recently-updated N); `member_sponsored` index rows show it once they cycle through enrichment. **Next for bills:** widen enrichment past the current cap toward the full corpus.

**2026-07-24 — Finance hardening + coverage; ruff pinned; ZIP self-discovery; Mastodon**
Post-deploy fixes from the finance rollout. **FEC key wiring:** `FEC_API_KEY` (+ `FEC_CYCLE`) added to the backend `environment:` block in `docker-compose.yml` — a value in `.env` alone is only used for `${...}` substitution and never reached the container (same mechanism as `CONGRESS_GOV_API_KEY`). **Rate limits:** the per-member `/candidate/{id}/totals` design (~537 calls) blew past api.data.gov's ~1000/hr, so only ~30% loaded; rewrote `fec_finance` to the **bulk** `/candidates/totals` endpoint (a handful of paginated calls per chamber). **Coverage:** a single cycle only lists candidates running *that* cycle, so ~2/3 of senators were missing — now sweeps `_CYCLE_SPAN` cycles (newest-first, first row wins) so every Senate class + the House is covered. **Deploy hot path:** `refresh` (deploy step) runs CORE only (`members`, `bills`, `votes`); `sponsored_bills`/`finance`/`zip_districts` moved to `EXTRA_REFRESHERS` (scheduler + `python -m app.pipelines.refresh <name>|all`). **Lint:** added `backend/ruff.toml` (deterministic `select = [E,F,UP,B]`, ignore `B008`, exclude `migrations/`) because CI's unpinned ruff kept turning red on default-ruleset drift; fixed one real UP017 (`datetime.UTC`). **ZIP:** `zip_crosswalk` now discovers its file from the Census directory listing (the hard-coded name 404'd). **Frontend:** dropped the X/Twitter social link, added Mastodon (`site-config` + a `mastodon` `BrandIcon` glyph).

**2026-07-23 — Member-data accuracy fixes + campaign finance (Increment 4a)**
Paused feature work to fix member-data accuracy and add the first financial data. **Accuracy:** (1) "In office since" showed the *current* term's start (Jan 3 2025 for everyone re-elected into the 119th) — added `members.served_since` (0006), computed by walking back through contiguous same-chamber terms (Cantwell → 2001, Rogers → 2003; `term_start` kept, now meaning "current term began"). (2) Sponsored-bill counts reflected only the 250-bill enriched slice — added a per-member pipeline (`congress_member_sponsored`) hitting `/member/{bioguide}/sponsored-legislation` for the current Congress and upserting bill "index" rows (identity + title + latest action, sponsor = the member) **without** touching the enriched actions/cosponsors; the member endpoint now returns the true `sponsored_bills_total`. (3) Moved the Source-IDs strip to the bottom of the member page. **Finance (Increment 4a):** `member_finance` table (0007; per member per cycle) + `fec_finance` pipeline pulling OpenFEC `/candidate/{id}/totals` for each member's current-office FEC candidate id (chosen by `S`/`H` prefix) — receipts / disbursements / cash-on-hand / debts + the individual-vs-PAC-vs-party receipts split; key sent as the `X-Api-Key` header, never a URL param. New `FinanceCard` renders topline tiles + a proportional receipts-source bar on the member page. Requires `FEC_API_KEY` (free DATA.gov key) — **fail-soft/skipped without it**, exactly like the bills pipeline. Both new pipelines read the legislators staging file (DB-free) and register in `refresh_all` (+ daily scheduler jobs). **Budget note:** each deploy's `refresh_all` now adds ~537 Congress.gov + ~537 OpenFEC calls; both back off on 429. **Next:** named top donors + industries (OpenSecrets / Schedule A itemization), and widen bill/vote coverage.

**2026-07-23 — Congress dashboard + self-contained seat map + ZIP→reps lookup; front-page polish**
Turned the platform entry into a visual view of Congress. **Backend (all additive):** `zip_districts` table (0005; composite PK `(zip, state, district)`) + `zip_crosswalk.py` pipeline (public **Census ZCTA↔CD relationship file** — no auth, fetch-at-refresh like every other source; resolves the ZCTA/CD columns *by name prefix* and tries `cd119`→`cd118` so a redistricting-year publish gap can't break the pull; drops water-only slivers) + `normalize/zip_districts.py` (full delete+reload, chunked under the 32767-param cap), registered in `refresh.py` + a monthly scheduler job. New `routers/congress.py`: `/api/map` (party/link index keyed `STATE-DISTRICT` for the House, by state for the Senate — derived **entirely from `members`, zero new data dependency**), `/api/summary` (per-chamber D/R/I balance), `/api/lookup?zip=` (5-digit-validated → your senators by state + representative(s) by state+district; a boundary-straddling ZIP returns every match). **Frontend:** `/congress` (`force-dynamic`) is now the platform entry — `siteConfig.appUrl`, both "Enter GovMap" CTAs, and a new "Congress" nav item point here. `CongressCartogram` is a **self-contained computed hemicycle**: every seat is one member, party-colored from `/api/map`, hover-to-identify, click→profile, House/Senate toggle — no map tiles, no geometry files, no third-party requests (chosen over a geographic polygon map because district geometry can't be produced on the static build box — the geographic upgrade is deferred, see open items). `ZipLookup` + `CongressExplorer` tie the ZIP box to the chart (your reps get ringed); `ChamberSplit` shows the two chambers with party-balance bars; `/members` gains `[All|House|Senate]` tabs (`?chamber=`). **Front-page polish:** hero → "See your **government** clearly." (white-on-blue highlight box + red *clearly.*); the "Enter GovMap"/"How it works" CTAs are solid-but-glassy; the header bar is full-width (logo pinned far-left, nav far-right).

**2026-07-23 — UX visual polish (Gemini) + Claude finalize pass**
First real run of the Claude-builds / Gemini-polishes loop ([[gemini-division-of-labor]]): Gemini restyled the detail pages, `DetailKit`, roster, and search into a cohesive light "civic dashboard" (member profile header + stat strip, a proportional yea/nay tally bar and by-position grouping on votes, a vertical action timeline on bills, chair/ranking-hoisted committee rosters, member cards with avatars, a polished dark search dropdown) — no new dependencies, server/client boundaries intact. Claude's finalize pass then reconciled where Gemini's design outran the API contract: added `photo_url` to the bill-sponsor and committee-member query+response (so their avatars have a source) and to the matching `lib/api` types; added a `CommitteeMember` type alias; corrected the votes `totals` annotation to `Record<string, number | null>`; fixed the search empty-state check (it was counting the `query` string) and an invisible party dot; dropped unused imports. Lesson for future Gemini hand-offs: it will reach for fields/types that "should" exist — the finalize pass owns reconciling the data contract.

**2026-07-23 — Platform UX baseline: detail pages + universal search**
Turned the Legislative data into a navigable platform (the "SIEM for government" surface). **Backend:** `/api/search` — one grouped typeahead endpoint over members/bills/votes/committees (bound-parameter ILIKE with escaped LIKE metacharacters, length-bounded query, hard per-group caps; structured to add entity types). **Frontend baseline (Claude builds wiring + a plain-but-consistent baseline; Gemini does the visual polish — see [[gemini-division-of-labor]]):** `lib/api.ts` (typed responses + `serverApiBase()` vs build-time `publicApiBase`, `apiGet` that maps 404→notFound), `components/DetailKit.tsx` (shared server-safe primitives — `Section`/`Stat`/`PositionPill`/`CodePill`/`BackLink` + party/date helpers — the single restyle target), and four SSR detail pages: `/members/[bioguide]` (bio, cross-source IDs, committees, sponsored bills, voting record), `/bills/[billId]` (sponsor, action timeline, cosponsors), `/votes/[voteId]` (tallies + every member's position), `/committees/[committeeId]` (majority/minority roster). Every entity cross-links by bioguide, so a search result → member → their votes → a vote → other members all navigate. `components/UniversalSearch.tsx` is a debounced/abortable client typeahead wired into `SiteHeader` (centered on desktop app pages, in the mobile menu to keep the fixed-header height constant so `pt-24` still clears it); the roster rows now link to detail. All detail pages are `force-dynamic` (backend unreachable at image build). Deferred/next: visual polish (Gemini), a ZIP→district Mapbox map, bill/vote list pages, keyboard nav in search.

**2026-07-23 — Votes (Increment 3b — House Clerk + Senate LIS)**
Roll-call votes from the two authoritative XML sources, and the **id_crosswalk's first real cross-source payoff**. **Schema (0004):** `votes` (keyed `{h|s}{congress}-{session}-{roll}`, chamber/date/question/result/bill_id/totals JSONB/source_url) + `vote_positions` ((vote_id, bioguide_id), position). bioguide indexed, not FK (same current-only reasoning as bills). **Pipelines (a third source shape — parsed XML, so no Pydantic `*Raw`; manual `xml.etree` parse that skips bad rows, fails if none):** `house_clerk_votes.py` (clerk.house.gov/evs/{year}/roll{NNN}.xml — binary-searches the current max roll, pulls the most-recent VOTES_LIMIT newest-first; **House `name-id` IS the Bioguide ID** → positions join members directly) and `senate_lis_votes.py` (LIS menu → newest N individual vote files; **Senate keys members by `lis_member_id`, NOT bioguide**). **Both set a descriptive `User-Agent`** — the Clerk 403s the default requests UA. **Normalizer** `votes.py` loads a `id_crosswalk.lis → bioguide` map and resolves every Senate position through it (unresolved positions skipped + counted); House positions bind bioguide directly. Chunked inserts under the 32767-param cap (100 House votes × ~435 members ≈ 43k position rows). **Orchestration:** one `refresh_votes` runs both chamber pulls independently (one down → 'partial', both down → raise), then the shared normalizer; 30-min scheduler interval. **API:** `/api/votes` (filter chamber/congress/session/bill_id) + `/api/votes/{vote_id}` (every position, names left-joined); `/api/members/{bioguide}` gains `voting_record`. Config: `CONGRESS_SESSION` (2 = 2026), `VOTES_LIMIT`. Legislative core (members, committees, bills, votes) now flows end-to-end for the 119th.

**2026-07-22 — Bills (Increment 3a — Congress.gov)**
First data from the Congress.gov v3 API: current-Congress bills with sponsor, action timeline, and cosponsors. **Schema (0003):** `bills` (keyed `{type}{number}-{congress}`, e.g. `hr1-119`), `bill_actions` (per-bill timeline, full-replaced each refresh), `cosponsors`. Sponsor/cosponsor bioguide columns are **indexed but not FKs** — a bill's actors can include members no longer in the current-only `members` table; bioguide stays the logical join key without enforcing RI across that boundary. `status` is intentionally minimal (only the source-derived "Became Law"); the full truth lives in `bill_actions` (data-only, no invented status taxonomy). `summary_plain_english` exists but stays null (LLM work on hold). **Pipeline** (`congress_gov_bills.py`): bounded + incremental — pulls the most-recently-updated bills (`sort=updateDate desc`) up to `CONGRESS_GOV_BILL_LIMIT` (default 250), each enriched with detail + actions + cosponsors, so scheduled runs keep the "what's moving" set fresh and raising the cap widens coverage. The API key is sent as the **`X-Api-Key` header, never a URL param**, so it can't leak into exceptions/logs/`pipeline_status.detail`. **Normalizer** re-validates staged JSON through the `*Raw` schemas (so dates deserialize to `date` objects) and chunks inserts under Postgres' 32767-param cap. **API:** `/api/bills` (filter by congress/type/sponsor/policy_area) + `/api/bills/{bill_id}` (sponsor + actions + cosponsors, names left-joined from members); `/api/members/{bioguide}` gains `sponsored_bills`. Registered in `refresh.py` + scheduler (30-min interval). Config: `CONGRESS_NUMBER` (119, bump in 2027), `CONGRESS_GOV_BILL_LIMIT`. **Next: 3b — votes** (House Clerk XML + Senate LIS XML → `votes`, `vote_positions`; Senate votes arrive keyed by LIS ID, resolved to bioguide via `id_crosswalk` — the crosswalk's first real payoff).

**2026-07-22 — Legislative foundation (Increments 0-2 of the branch build)**
Started the Legislative-branch build-out (current 119th Congress; see the approved plan). **Schema (0002):** extends `members` (birthday/gender/contact/social/in_office/leadership_role) and adds `id_crosswalk` (the Bioguide → FEC/OpenSecrets/govtrack/… join backbone), `committees` + `committee_memberships`, and promotes `pipeline_status` from a JSON file to a table. Models live in `app/models/` and are all imported in `migrations/env.py`. Migration is hand-written (mirrors `0001`) since the build box has no Alembic; it applies on the server via `alembic upgrade head` at container start. **Observability (Inc 1):** `app/pipelines/status.py::record_run()` persists per-source status (+ optional `ALERT_WEBHOOK_URL`); `app/pipelines/refresh.py` is the single pull→normalize→status orchestration that both the scheduler and `scripts/deploy.sh` call (`python -m app.pipelines.refresh`); `app/scheduler.py` is now a job registry; `/internal/pipeline-status` reads the table. **Data (Inc 2):** the `congress_legislators` pipeline now stages three files (legislators + committees-current + committee-membership-current) and normalizers populate members (enriched), `id_crosswalk`, `committees`, and `committee_memberships`. **API:** `/api/committees` (+ `/{id}` detail with members) and `/api/members/{bioguide}` (detail with cross-source IDs + committee seats). Later increments: bills/votes (0003), finance/lobbying/disclosures (0004), member detail page (Inc 5).

### The golden pipeline pattern (clone this for every new source)

`congress_legislators` is the reference. A source is three layers, one file each:
1. **Pipeline** (`app/pipelines/<source>.py`): pull → validate with a Pydantic `*Raw` schema (skip individually bad rows, raise if none survive) → write staging JSON. DB-free (network + filesystem only). Runnable via `python -m ...`.
2. **Normalizer** (`app/normalize/<entity>.py`): read staging → map to canonical rows (apply the Bioguide/ID-crosswalk + ISO-8601 rules) → `pg_insert(...).on_conflict_do_update(...)` upsert.
3. **Orchestration + API**: register a `refresh_<source>()` in `app/pipelines/refresh.py` (`REFRESHERS`) and a cadence in `app/scheduler.py` (`JOBS`); add a router in `app/routers/`. `refresh_<source>()` records status via `record_run()`.

Two reference implementations exist to clone from:
- **Bulk-file source** → `congress_legislators` (one download, validate a list, stage). Best when the source publishes a full dataset.
- **Keyed REST API** → `congress_gov_bills` (paginate a list endpoint, then per-key fetch detail + sub-resources; bounded + incremental via an update-date sort; auth key in a **header**, never the URL; chunked inserts under Postgres' 32767-param cap; re-validate staged JSON in the normalizer so dates round-trip). Best for api.congress.gov / api.data.gov / FEC-style APIs.

**2026-07-22 — Design system + landing/app polish pass**
Comprehensive front-end design pass establishing a shared system the whole app inherits. Typography via `next/font` (Space Grotesk display + Inter body → CSS vars, wired into Tailwind `fontFamily`). New shared components: `SiteHeader` (fixed, glass-on-scroll, mobile hamburger; `marketing`/`app` variants), `SiteFooter` (Capitol backdrop, Explore/Project/Legal columns, social icons), `Reveal` (IntersectionObserver scroll-fade, reduced-motion-safe), `LegalLayout`. Landing hero gets a staggered on-load fade-up (pure CSS) and stronger scrim; About/Support fade in on scroll. Draft `/privacy` and `/security` pages. Root body is now navy so mobile overscroll blends into the dark hero/footer (iOS paints only the root bg-color in the rubber-band, so color-matching is the reliable fix). Added OpenGraph/Twitter card metadata (Capitol image) for rich social shares. Social links are placeholder `@govmapus` (X/Bluesky/Instagram) pending real accounts. Tokens: `govnavy-800`, `fade-up`/`fade-in` keyframes, `shadow-card`. No new runtime dependencies (motion is CSS + a tiny observer; icons stay inlined). **Note:** `next/font/google` fetches fonts at build time — the Docker build needs network (it already has it for npm).

Follow-up tweaks: header gained a **Sign in** link → `/account` placeholder ("accounts coming soon" — real auth/benefits TBD by the user); hero heading recolored for legibility over the bright image ("See your" white, "government." govred, "Clearly." bright blue `#5cb3ff`) with text-shadows, subtext brightened to white; hero copy updated ("end-to-end live-synced view", "No press. No spin.").

**2026-07-22 — Landing page: Capitol hero, transparent logo, support links**
Redesigned the marketing hero with a US Capitol sunset photo (`public/capitol-hero.jpg`) behind a navy gradient for legibility. Fixed the "off-color box" logo: the logo PNG's baked background is `#0A0E1E` but the page navy is `#070B1A`, so it read as a rectangle — generated `logo-dark-transparent.png` (alpha-keyed the dark background out, verified clean) and use it as the home-button logo everywhere on dark surfaces; the opaque `logo-dark.png`/`logo-light.png` are kept as the primary brand assets. Added a Support section with six active donation platforms (Patreon, Ko-fi, Buy Me a Coffee, Liberapay, Open Collective, thanks.dev) rendered with Simple Icons brand glyphs (`components/BrandIcon.tsx`, inlined — no icon dependency), plus a **"seeking a fiscal sponsor"** callout. `site-config` gained `supportLinks[]`; the unused `supportUrl` was removed.

**2026-07-22 — Redeploy hardening + full stack live in production**
Site live end-to-end at govmap.us through the dashboard-managed tunnel (marketing, `/members` with real portraits + party colors, 537 members). Made redeploy fully reproducible: root `.env.example` documents the two required secrets (`POSTGRES_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`); `deploy.sh` now writes a self-documenting `.env` on a fresh box and flags the missing tunnel token; README gained a "Rebuilding on a fresh box" runbook. The dashboard-managed tunnel's routes live in Cloudflare and survive a rebuild; its token is in `.env`. **Correction:** `.env` is not the only per-box state: PostgreSQL and persistent logs require separate recovery, and starting the deploy script is not a substitute for a verified restore. Tunnel ID `ebdeb681-961d-4321-8beb-2f14b35c6143`.

**2026-07-22 — Cloudflare Tunnel as a stack service**
Moved the tunnel from a per-box systemd unit (fragile: interactive `tunnel login`, on-disk credentials that can't live in the repo, and the source of a rebuild's Error 1033) into the compose stack. New `cloudflared` service runs a **dashboard-managed** tunnel via a token from `.env` (`CLOUDFLARE_TUNNEL_TOKEN`), under a `tunnel` compose profile that `scripts/deploy.sh` enables automatically when the token is present. Restoring that token reconnects the tunnel only; it does not recover the database or logs. Ingress (public hostnames → `http://frontend:3000` / `http://backend:8000`) is configured once in the Cloudflare Zero Trust dashboard; cloudflared shares the compose network so those service names resolve. The old CLI/systemd tunnel should be uninstalled (`sudo cloudflared service uninstall`) and its dashboard tunnel deleted.

**2026-07-21 — Single-source deploy script**
Added `scripts/deploy.sh` as the one deploy path: `git reset --hard origin/main` → ensure `.env` (generates `POSTGRES_PASSWORD` if missing) → `docker compose up -d --build` → poll `/health` (backend migrates on start) → refresh data (pipeline + normalize, non-fatal so a source outage can't fail the deploy) → prune → verify `photo_url` is populated. Idempotent, re-runnable, never touches `.env` or the Postgres volume. Takes `--no-data` for code-only changes. The GitHub Actions runner now just calls `bash /opt/govmap/scripts/deploy.sh`, so manual and automated deploys are literally the same script — no more copy-pasted command sequences, and a reliable manual deploy exists whenever the runner is down.

**2026-07-21 — Member photos + roster polish + branding**
Swapped `logo-dark.png`/`logo-light.png` for tight cropped lockups (the originals had large baked-in margins that made the wordmark render tiny) and resized every logo `<Image>` to the new ~3.13:1 aspect. Added **member portraits**: `normalize/members.py` now sets `photo_url` to the deterministic unitedstates/images URL (`https://unitedstates.github.io/images/congress/225x275/{bioguide}.jpg`, verified 200 image/jpeg) — no separate pull pipeline since the URL is fully derivable from the Bioguide ID. The roster renders them via a small `MemberAvatar` client component that falls back to initials on 404/missing, plus party-colored labels (govred/govblue). Added a targeted `.gitattributes` (LF for `*.sh`/`*.yml`/`Dockerfile`, binary for images) to end the CRLF churn and guarantee the deploy script stays LF on the Linux host.

Note: `photo_url` was previously left null by the normalizer (it was reserved for a separate images pipeline). Setting it deterministically means an existing DB needs one normalize run to backfill — future weekly scheduler runs handle it automatically.

**2026-07-21 — Closed the operational loop**
With the pipeline proven live, automated the parts that were manual. (1) **Auto-deploy**: `.github/workflows/deploy.yml` now runs on push to `main` via a self-hosted GitHub Actions runner on the VM — it `git reset --hard`s `/opt/govmap` to `origin/main` and `docker compose up -d --build`s (backend re-applies Alembic migrations on start). No SSH, no exposed ports. Runner install is a one-time server-side step (needs a GitHub registration token). (2) **Scheduler**: `backend/app/scheduler.py` (APScheduler, wired into the FastAPI lifespan) refreshes members weekly (Sun 07:00 UTC) so data no longer depends on a manual run. (3) **Secured `/internal/*`**: HTTP Basic Auth via `INTERNAL_USER`/`INTERNAL_PASSWORD`, locked by default when unset — it was reachable at `api.govmap.us/internal/*` with no auth. (4) **Fixed the roster cap**: the members query was hardcoded to `limit=535`, silently hiding the ~2 non-voting delegates the pipeline loads (537 total); raised to 600 on both API and frontend. This entry originally assumed a nightly `pg_dump` cron; the operator later reported that no backups are in place, so that cron cannot be assumed.

**2026-07-21 — Flattened frontend routing (fixed blank-page bug)**
The first deploy rendered blank: every page served HTML with no `<!DOCTYPE html>`/`<html>`/`<body>` (Quirks Mode + React #418/#423 hydration failure → React tore the tree down). Ruled out Cloudflare (Bot Fight Mode / JS Detections injection was a real but secondary red herring) and the middleware (removing it didn't help). Root cause: **the platform routes lived under `app/app/` — a route segment literally named `app` inside the App Router's own `app/` directory — which corrupted route resolution so Next.js used `app/app/layout.tsx` (a bare `<div>`, no `<html>`) as the root and skipped the real `app/layout.tsx` entirely.**

Fix: collapsed to a standard flat structure — marketing at `app/page.tsx` (`/`), members at `app/members/page.tsx` (`/members`), no nested `app/app/`, no middleware. **Deferred: the govmap.us / app.govmap.us subdomain split.** It required host-based rewriting (middleware or `app/app/` nesting) and was the source of this whole class of pain; re-introduce it only once the flat app is proven stable, using a tested approach (config-level `rewrites` or separate concerns). `cloudflared` still routes `app.govmap.us` → `localhost:3000`, which now just serves the same content as `govmap.us` — harmless; drop that ingress line when convenient. `middleware.ts` and `site-config`'s subdomain URLs were removed.

**2026-07-21 — Containerized deploy layer**
Added `backend/Dockerfile` (migrations-on-start + uvicorn, non-root) and a multi-stage `frontend/Dockerfile` (Next.js `standalone` output, non-root runner). Extended `docker-compose.yml` from Postgres-only to the full stack: `postgres` + `backend` (`127.0.0.1:8000`) + `frontend` (`127.0.0.1:3000`), all loopback-bound so `cloudflared` reaches them over localhost and nothing is publicly exposed. Server-side rendering in the frontend now reaches the backend over the internal compose network (`API_INTERNAL_URL=http://backend:8000`); `NEXT_PUBLIC_*` prod URLs are baked at build time via compose build args. First real production deploy target: the home Ubuntu VM behind the `govmap` cloudflared tunnel (govmap.us / app.govmap.us / api.govmap.us).

**2026-07-20 — Brand assets + marketing/platform split**
Received the first brand assets: `logo-dark.png` / `logo-light.png` (full lockups, opaque backgrounds baked in — not transparent, so they're placed as full-bleed treatments, not floated over arbitrary backgrounds). Sampled exact colors from the artwork rather than eyeballing hex values: navy `#070B1A`, red `#DD1922`, blue `#58A9E6`, now in `frontend/tailwind.config.ts` as `govnavy`/`govred`/`govblue`. Cropped a square Capitol-only mark from the dark logo (no source icon-only asset existed) for `frontend/app/icon.png`.

Split the frontend into two zones on one Next.js deployment: **govmap.us** (marketing site, `app/page.tsx`) and **app.govmap.us** (the platform, moved to `app/app/`), routed by hostname in `frontend/middleware.ts`. Cross-zone links (marketing's "Enter GovMap" button, the platform header's link back) go through `frontend/lib/site-config.ts` since they need to be absolute URLs, not relative paths, once the two zones are on different hosts in production. Social handles and a support/donation link are left empty in that config — nothing fake ships in the footer.

**2026-07-20 — Repo scaffold + pilot pipeline started**
Consolidated the original planning notes (six documents, written across earlier drafts with some mutual inconsistencies — see *Reconciliation notes* below) into this file, `README.md`, and `AGENTS.md`. Decided to prove the full pipeline contract (pull → validate → normalize → store → serve → display) on a single source — `congress-legislators` — end-to-end through a minimal FastAPI + Next.js stack, before parallelizing to the remaining 24 sources. LLM summarization and Redis caching are explicitly deferred (see `AGENTS.md` → Current explicit boundaries).

## Reconciliation notes

The original planning docs disagreed with each other in a few places. Resolved as follows:

- **Source count**: 25 sources (confirmed against the masterlist's own "25 total" tally).
- **JSON output count**: 24 canonical outputs — 23 domain outputs plus `pipeline_status.json` as the operational/health output. (One earlier doc's table listed only 23 total because it predated the addition of the Senate LDA and Financial Disclosures sources; another doc's checklist heading said "23 JSON output" but its own criteria table lists 24 — that was a leftover from before those two sources were added, not a real disagreement.)
- **Senate LDA source**: the original note that `lda.senate.gov` "shuts down June 30 2026" is confirmed and the site now redirects to **lda.gov**, with API docs at `lda.senate.gov/api/`. Build the `senate_lda.py` pipeline against the current `lda.gov` endpoint, not the legacy domain. API access is already in hand.
- **Repo folder structure doc**: discarded. It was carried over from an unrelated project (financial dashboard) and doesn't fit GovMap's domain. The structure actually in use is documented below under *Repository layout*.
- **Frontend framework**: Next.js (App Router), not the earlier draft's Vite + React Router.
- **Hosting**: self-hosted home VM behind `cloudflared` (no exposed ports), Tailscale-only SSH, GitHub Actions deploy — not the earlier draft's Hetzner VPS + Coolify. This is a deliberate cheap-and-temporary choice; see README's Tech stack section.
- **OpenSecrets bulk data license** ("free, non-commercial") confirmed compatible with GovMap's nonprofit, non-advertising model.

## Canonical source list (26)

Status: `pilot` = actively being built against right now, `planned` = designed for, not yet started, `on hold` = deferred by product decision (not blocked technically).

| # | Source | Branch/category | Status |
| --- | --- | --- | --- |
| 1 | Congress.gov API | Legislative | **pilot** (bills, enrichment, committee meetings) |
| 2 | unitedstates/congress-legislators | Legislative | **pilot** |
| 3 | unitedstates/congress (scrapers) | Legislative | planned |
| 4 | unitedstates/images | Legislative | planned |
| 5 | FEC API (OpenFEC) | Legislative/Executive | **pilot** (candidate finance totals) |
| 6 | OpenSecrets bulk data | Legislative | planned |
| 7 | Federal Register API | Executive | planned |
| 8 | SAM.gov Federal Hierarchy API | Executive | planned |
| 9 | OPM PLUM website | Executive | planned |
| 10 | USASpending.gov API | Executive | planned |
| 11 | CourtListener API | Judicial | planned |
| 12 | Free Law Project judge photos | Judicial | planned |
| 13 | Census Data API | Geographic | planned |
| 14 | Open States API | State legislative | planned |
| 15 | Census TIGER/Line shapefiles | Geographic | planned |
| 16 | Census Geocoder API | Geographic | planned |
| 17 | Census of Governments | State/local | planned |
| 18 | Legistar | Local legislative | planned |
| 19 | Municode | Local legislative | planned |
| 20 | openstates/people | State executive | planned |
| 21 | Supreme Court Database (WashU) | Judicial | planned |
| 22 | PACER | Judicial | planned |
| 23 | NCSC Court Statistics Project | State judicial | planned |
| 24 | Senate LDA Lobbying API (lda.gov) | Federal legislative | planned — API access confirmed in hand |
| 25 | Congressional Financial Disclosures | Legislative/Judicial | planned |
| 26 | Census ZCTA↔CD relationship file | Geographic | **pilot** (ZIP→district lookup) |

## Canonical JSON outputs (24)

`members.json`, `votes.json`, `bills.json`, `campaign_finance.json`, `executive_officials.json`, `executive_actions.json`, `agencies.json`, `judges.json`, `opinions.json`, `spending.json`, `districts.json`, `scotus_cases.json`, `federal_cases.json`, `state_legislators.json`, `state_bills.json`, `state_executives.json`, `state_court_stats.json`, `state_districts.json`, `demographics.json`, `government_finances.json`, `local_legislation.json`, `local_officials.json`, `lobbying.json`, `financial_disclosures.json`, plus `pipeline_status.json`.

Field-level schemas per output carry over from the original planning docs unchanged; they're not reproduced here to avoid a second copy drifting out of sync — add them to the relevant Pydantic schema module as each output is actually built, since that's the version that has to be correct.

Note: `bills.json`, `executive_actions.json`, `opinions.json`, and `state_bills.json` originally specced a `summary_plain_english` field. That field is not being populated right now — see `AGENTS.md` → Current explicit boundaries. The schemas keep the field as nullable so it can be filled in later without a breaking migration.

## Repository layout

```
govmap.us/
├── backend/            # FastAPI app: pipelines, normalization, API
│   ├── Dockerfile      # migrations-on-start + uvicorn, non-root
│   ├── app/
│   │   ├── pipelines/  # one script per source, Layer 1
│   │   ├── normalize/  # one module per entity, Layer 2
│   │   ├── routers/    # API endpoints, Layer 3
│   │   ├── models/     # SQLAlchemy ORM models
│   │   ├── schemas/    # Pydantic validation/response models
│   │   ├── db.py
│   │   ├── config.py
│   │   └── main.py
│   ├── migrations/     # Alembic
│   └── data/staging/   # raw pipeline output, gitignored
├── frontend/           # Next.js app -- two zones, one deployment
│   ├── Dockerfile      # multi-stage, Next standalone output, non-root
│   ├── middleware.ts   # hostname routing: govmap.us vs app.govmap.us
│   ├── lib/
│   │   └── site-config.ts  # cross-zone URLs, GitHub, social/support links
│   ├── public/         # logo-dark.png, logo-light.png
│   └── app/
│       ├── page.tsx    # marketing site (govmap.us root)
│       ├── icon.png    # favicon (cropped Capitol mark)
│       └── app/        # the platform (app.govmap.us root, via rewrite)
│           ├── layout.tsx
│           ├── page.tsx
│           └── members/page.tsx
├── docker-compose.yml  # full stack: postgres + backend + frontend, loopback-bound
└── .github/workflows/  # CI (lint now, deploy once the runner exists)
```

## Phase checklist

Adapted from the original end-to-end plan, reordered to prove the pipeline contract on one source before fanning out — see the 2026-07-20 build log entry for why.

- [x] Repo scaffold, `.gitignore`, three canonical docs
- [ ] **Pilot**: `congress-legislators` pipeline → normalize → `members` table → `/api/members` → Next.js list page, running locally end-to-end
- [ ] Local dev loop verified (Postgres via `docker-compose`, backend, frontend all running together)
- [ ] CI: lint workflow green on push
- [ ] Fan out to remaining 24 source pipelines (Layer 1), reusing the pilot's pattern
- [ ] Normalization layer for all entities (Layer 2), `id_crosswalk` table populated
- [ ] All 24 JSON outputs live (Layer 3)
- [ ] FastAPI backend complete: all endpoints, Redis caching added *when needed*, APScheduler wiring
- [ ] Next.js frontend — Legislative branch complete
- [ ] Next.js frontend — Executive & Judicial branches
- [ ] Full cross-branch bill pipeline view
- [ ] Security hardening pass (rate limiting, CORS, dependency audit, load test)
- [ ] Self-hosted GitHub Actions runner + Tailscale deploy wired up
- [ ] Production launch on the home VM
- [ ] Post-launch: 30-day stability, then revisit LLM summarization with a real review process, then migrate to paid infrastructure once funded

## Known open items

- **PACER costs money per page**, not a flat quarterly fee — the pipeline needs to scope queries tightly and track spend, not just cap at "$30/qtr" and assume it holds.
- **OPM PLUM and White House scrapers are fragile by nature** (HTML scrapes with no API). They need to fail loudly on structural change, not silently return stale data — flagged in the original plan and still true.
- **Pipeline status is persisted in Postgres** (the `pipeline_status` table / `PipelineStatusRow`), written by `record_run()` and read by `/internal/pipeline-status`, so it survives restarts and redeploys. This supersedes the old ephemeral `pipeline_status.json` (promoted to a table in schema 0002) — no volume/permission concern remains. A fresh DB simply shows no rows until each source's first run.
- **2027 rollover: the tracked Congress/session/cycle are time-coupled and must be bumped together in January 2027.** All three are env-overridable (change the deploy `.env` + `docker-compose.yml` defaults, not code): `CONGRESS_NUMBER` 119 → 120, `CONGRESS_SESSION` 2 → 1 (120th's first session = 2027), and `FEC_CYCLE` 2026 → 2028. Defaults live in `backend/app/config.py`; the runtime values are wired in the backend `environment:` block of `docker-compose.yml`. Roll all three at once — a mismatch (e.g. new Congress but old cycle) silently pulls the wrong session's bills/votes or the wrong finance cycle. The per-run coverage caps (`CONGRESS_GOV_BILL_LIMIT`, `VOTES_LIMIT`) don't need touching; only these three values.
- **Marketing site has no real social handles or support/donation link.** `frontend/lib/site-config.ts` ships with `socialLinks: []` and `supportUrl: null` on purpose rather than placeholder/fake links — fill them in as real accounts and a donation link exist.
- **Favicon is a stopgap crop**, not a designed icon mark — see README → *Sites & branding*. Fine for now, worth revisiting once there's a proper icon-only asset.
- **DNS not yet configured** for the `app.` subdomain split. `frontend/middleware.ts` assumes `app.govmap.us` resolves to the same deployment as `govmap.us` — that DNS record (and matching `cloudflared` routing) needs to exist before the split works in production.
- **The `/congress` map is a computed seat-chart, not geographic.** `CongressCartogram` draws one dot per member (a hemicycle) because congressional-district geometry can't be generated or downloaded on the static build box. The geographic upgrade — real district polygons — is deferred; when built it must stay self-contained (serve simplified geometry from our own API or a committed asset, **never** per-visitor third-party map tiles/tracking).
- **Campaign finance needs `FEC_API_KEY`.** `fec_finance.py` (OpenFEC candidate totals) is fail-soft: without a free DATA.gov key it records a non-fatal error and the member page shows no finance section. The key must be **both** in the VM `.env` **and** wired into the backend `environment:` block in `docker-compose.yml` (a value in `.env` alone is only used for `${...}` substitution — it isn't injected into the container automatically; same as `CONGRESS_GOV_API_KEY`). Topline totals + the Form 3 receipts breakdown (0009) and **named itemized donors** via on-demand Schedule A caching (0010, Increment 4b) are now built. **Donor _industries_** (CRP industry codes via OpenSecrets, own key/attribution — kept a separate taxonomy from NAICS per AGENTS.md) remain the next finance step.
- **Deploy runs CORE sources only.** `python -m app.pipelines.refresh` (the deploy step) refreshes just `members`, `bills`, `votes` — fast and well-behaved. The heavier / slow-cadence sources (`sponsored_bills`, `finance`, `zip_districts`, `committee_meetings`, `backfill_bills`) are in `EXTRA_REFRESHERS`, kept off the deploy hot path: they run on their own scheduler cadence (see `app/scheduler.py`) and on demand via `python -m app.pipelines.refresh <name>` (or `all`). A fresh environment should run `refresh all` once after the first deploy. (`donations` and bill enrichment-on-view have **no** refresher — they populate lazily at request time.)
- **FEC finance queries by candidate id (targeted, ~20 calls).** `fec_finance` calls `GET /candidates/totals` filtered to **our members' candidate ids in batches of 50** (repeatable `candidate_id` + `cycle` params, `sort=-cycle`, newest wins across the last `_CYCLE_SPAN` cycles). This covers all three Senate classes + the House in ~20 targeted calls — no scanning the ~3500-candidate field, and well under api.data.gov's ~1000 req/hr. Earlier designs (one call per member ~537; then an untargeted per-cycle bulk sweep ~100+) both burned the hourly budget. Idempotent (upsert on `(bioguide, cycle)`). **The budget still resets hourly** — if a run 429s because the hour is already spent (from prior runs), wait for the reset and run once.
- **Ruff is pinned via `backend/ruff.toml`.** CI runs an unpinned `pip install ruff`, whose default rule set shifts between releases; without a config, a new ruff version turned the lint red on unchanged code (B008 on every FastAPI `Depends`, UP on Alembic boilerplate, BLE/DTZ on intentional patterns). The config sets a deterministic `select = [E, F, UP, B]`, ignores `B008` (FastAPI idiom), and excludes `migrations/`.
- **ZIP crosswalk uses HUD (needs `HUD_API_TOKEN`).** Confirmed via directory listing that Census publishes **no** ZCTA↔CD relationship file (`rel2020/zcta520/` pairs ZCTA with county/place/tract/tabblock/cousub only). `zip_crosswalk.py` now uses the authoritative **HUD USPS ZIP→CD crosswalk** (huduser.gov, type 5), token as a Bearer header. Free token from huduser.gov; must also be in the backend `environment:` block (it is: `HUD_API_TOKEN`). Fail-soft without it — `/api/lookup` returns empty and the `/congress` ZIP box shows "couldn't match" until it's set + `refresh zip_districts` runs.
