# GovMap platform roadmap

Prepared: 2026-11-11 UTC.

**Status: proposed execution plan, not an implementation or deployment approval.**
The product direction below reflects operator decisions. Numerical service
targets, source-specific designs, paid access and later product phases need
validation and approval at their respective gates.

## 1. Mission and approved direction

Build a source-grounded, near-real-time view of the US government: institutions,
people, decisions, legal authority, money, oversight and their history. The
website is one interface to that data platform, not the platform's boundary.

The approved direction is:

- Stabilize existing code while adding data in small, independently verifiable
  releases. Security, recoverability and data correctness are release gates.
- Federal first, then state, then local.
- Maintain a long-term catalog of every discoverable public federal dataset,
  prioritizing government operations and accountability for deep integration.
- Ingest current data and full available history together through separate
  work lanes. History is not an indefinitely deferred feature.
- Remain an open-source project now. A business API and user/tenant per-seat
  offerings are future possibilities, not authorization to build accounts,
  billing or tenancy today.
- Leave comprehensive site-monitoring infrastructure on hold. Existing health
  checks and backup heartbeat remain. Per-run data-quality evidence is still
  required to know whether ingestion is correct.

No LLM-generated summaries, speculative Redis layer, user accounts or new
monitoring service are introduced by this plan. No paid access, purchases,
production changes or destructive migrations are authorized here.

## 2. Definition of coverage

"All federal data" is a continuing discovery obligation, not a finite count of
APIs. Government inventories change, datasets overlap, and some material is
restricted, unpublished, unavailable, licensed, fee-based or not machine-readable.
The platform must distinguish these cases instead of promising universal access.

Track five independent dimensions:

1. **Discovery:** a dataset exists in the catalog, with publisher and access link.
2. **Integration:** records are actually ingested, validated and queryable.
3. **History:** specific available periods and revisions have been acquired.
4. **Freshness:** current changes meet a source-appropriate measured objective.
5. **Relationships:** identifiers and evidence support the displayed joins.

A catalog entry is not an integrated dataset. A large row count is not evidence
of completeness. A successful request is not a successful ingestion. No records
returned is not equivalent to no government activity.

For each dataset publish a coverage state:
`discovered`, `assessing`, `integrating`, `current-partial`, `current-verified`,
`historical-backfill`, `verified-for-declared-range`, `restricted`, `unavailable`,
`retired`, or `deferred-with-reason`. Implementation may refine these names;
current coverage and history must remain separate fields, not one misleading flag.

### Federal-to-state transition gate

Federal discovery never stops. Opening the state phase requires:

- Every federal operations/accountability domain in section 7 has a coverage
  decision, with supported domains integrated and verifiable.
- Current coverage and explicitly declared historical ranges reconcile against
  available authoritative inventories; missing periods and records are listed.
- Source-access, legal, cost and publication gaps have named dispositions.
- No unresolved critical/high exploitable issue or known material silent data
  corruption in the release path.
- The operator explicitly accepts the federal coverage report and any remaining
  backfill or long-tail gaps before starting state implementation.

This is not permission to call unfinished federal work complete. If the
operator requires a remaining federal source first, state work waits.

## 3. Verified starting point and immediate reconciliation

Planning baseline: repository commit
`6727148a36de669592251267f44e2f6835d77019`.
See [build history](../CODE-MANIFEST.md) and [deployment documentation](../README.md).

Operational evidence already recorded:

- Separate production and test deployments, private service-name resolution,
  and distinct database credentials.
- Consistent database/log bundles, off-site copies and successful restore
  rehearsals. Configuration and recovery credentials are held separately.
- Backend readiness, frontend end-to-end health and build commit reporting.
- A dev-only backend interruption returned HTTP 503; recovery returned 200.
  Production remained healthy.
- Production and dev previously matched CI-tested release `5652b7f`.
  This does not establish that every later repository commit is deployed.

The current data application is principally federal legislative: current
members/crosswalks, bills and enrichment, votes, committees and meetings, FEC
finance/donations, and HUD ZIP-to-district lookup.

Important code facts shaping this plan:

| Evidence | Consequence |
| --- | --- |
| [Scheduler](../backend/app/scheduler.py) runs eight refresh jobs; on the deployment platform they run in a separate [worker](../backend/app/worker.py) (2026-11-11), not the API process. | Restarts, concurrency and worker ownership need explicit treatment before scaling ingestion. |
| [Bill pull](../backend/app/pipelines/congress_gov_bills.py) uses a capped recent-update listing. | Repeated recent-page pulls do not prove all changes or historical bills are eventually covered. |
| [Pipeline status](../backend/app/models/pipeline_status.py) stores one latest row per source. | Run history, durable checkpoints and completeness evidence are not yet represented by that table alone. |
| [Batch policy](../backend/app/pipelines/batch.py) can classify some item failures as `ok`. | Successful transport, coverage completeness and source freshness need distinct semantics. |
| [Members](../backend/app/normalize/members.py) and [crosswalk](../backend/app/models/crosswalk.py) are current-roster oriented. | Historical people and office terms need explicit models before wide backfills. |
| [Bill text](../backend/app/models/bill.py) retains a latest-version cache; several historical references intentionally lack foreign keys. | Version history and unresolved historical joins must be designed, not inferred from current rows. |
| [Donation cache](../backend/app/services/donations.py) keeps mutable fetch progress alongside request-time fetching. | Concurrent requests, duplicate receipts, counts and rollback need regression coverage. |

**First blocker:** the baseline contains
[request regression tests](../backend/tests/test_request_stability.py),
[HUD completion tests](../backend/tests/test_zip_crosswalk_completion.py), and
the [search helper](../backend/app/services/search.py), but several corresponding
producer changes are absent from this checkout:

- Internal authentication still compares strings directly.
- The existing webhook sender still does not inspect HTTP rejection.
- Donation search still builds an unescaped LIKE pattern.
- HUD pagination still returns after exhausting its cap without failing closed.

These are observations of the current files, not a claim about why the release
history changed. Reconcile source, tests, CI and deployed SHAs before relying on
the earlier "implemented" report. Do not copy old patches blindly.
All four producers are implemented in the R0 working tree; see the R0 status
below.

The older source inventory and phase checklist in the build manifest are
historical planning material. They include superseded hosting, status-file and
ZIP-source assumptions. Use current code and verified publisher documentation,
not the old source count, to drive the new coverage catalog.

## 4. Non-negotiable engineering invariants

### Identity and provenance

- Preserve the existing pipeline -> normalization -> database/API separation.
- Federal legislative people join by Bioguide; FEC candidate identifiers remain
  arrays with cycle context. State/local people and jurisdictions use OCD.
- Geographic joins use authoritative geographic identifiers/FIPS with type and
  vintage. A bare FIPS string is not globally unique across geography types or
  historical boundaries. ZIPs are postal areas, not exact voting districts;
  retain ambiguous mappings instead of guessing one representative.
- Store CGAC on both agency and spending sides. Model other agency code
  systems and code changes as crosswalks, not interchangeable strings.
- Do not force executive officials or judges without Bioguide IDs into a
  legislative-person table. Approve an entity-specific source-ID strategy
  before coding those sources; record mappings and uncertainty.
- No silent name-only joins. Uncertain cross-branch matches require evidence,
  provenance and documented manual adjudication.
- Keep CRP industry and NAICS taxonomies distinct.
- Preserve source URL, source-native ID, publisher, record/version identifier,
  retrieval time, available source publication/update time, content hash and
  normalizer/schema version. Retain only raw material lawfully reusable.
- Distinguish event time, effective time, source publication time, observation
  time and local ingestion time. Unknown times remain unknown. Preserve
  date-only precision rather than fabricating midnight timestamps.
- Corrections and amendments create traceable revisions; they must not erase
  the evidence explaining an earlier published state.

### Safe writes and honest results

- Idempotent writes and resume cursors are tested together.
- Never advance a completeness checkpoint past failed or quarantined records
  without an explicit unresolved-gap record and retry mechanism.
- Validate a destructive snapshot before replacing live rows. Empty, truncated,
  repeated-page or sharply shrinking data must not silently erase good data.
- Publish multi-table source changes atomically where consistency requires it;
  do not keep database transactions open during slow network calls.
- Separate last attempt, last valid update, last complete reconciliation and
  authoritative freshness. A fallback or partly successful batch cannot certify
  official coverage.
- Use deterministic fixtures and isolated integration databases. No live
  government credentials in tests, fixtures, logs or pull requests.

## 5. Source-aware near-real-time objectives

These are **proposed service objectives**, not existing guarantees. Calibrate
with measured publisher behavior, rate limits and operating capacity before
committing publicly.

| Source behavior | Initial target after a change becomes publicly accessible |
| --- | --- |
| High-value legislative events, published opinions, executive actions | Poll or use supported events every 5-15 minutes where permitted; aim for p95 discovery-to-published availability within 30 minutes. |
| Rulemaking dockets, meeting schedules and frequently changing records | 15-60 minute discovery intervals; p95 processing within 30 minutes of discovery. |
| Daily releases, finance filings, organization changes | Collect each published release or reconcile daily; generally within 24 hours of availability. |
| Quarterly/annual/bulk datasets and historical archives | Follow publisher release cadence; track backfill throughput and coverage, not a fictitious minute-level freshness promise. |

Measure separately:

- **Publisher lag:** event to publication, only where both times are known.
- **Discovery lag:** public availability to first observation, only where
  availability is evidenced. Otherwise report observation/poll intervals,
  not an invented availability timestamp.
- **Processing lag:** first observation to successful publication by GovMap.
- **Coverage lag:** unresolved records/partitions behind the current watermark.

Show source, last checked, last authoritative update, current/historical
coverage and degraded status in APIs and relevant UI views. An unchanged
dataset can be fresh; a repeatedly fetched stale source cannot be made fresh
by updating a local timestamp.

Initial release acceptance proposal: at least seven consecutive days of dev
or supervised production evidence, at least two real source executions, and
one injected outage/recovery scenario. For monthly/annual sources use replayed
prior releases plus the next genuine release before claiming cadence compliance.
Do not accelerate live scraping merely to finish a test.

## 6. Two ingestion lanes, one authoritative data model

Every newly integrated source ships both:

1. **Current lane:** discover changes, ingest incrementally, reconcile late
   corrections with overlap windows, and maintain current views.
2. **Historical lane:** enumerate full available periods, acquire bulk releases
   where possible, checkpoint partitions and resume interrupted backfills.

Both use the same validators, identity rules and version-aware upsert logic.
An older backfill must never overwrite a newer accepted revision. Sources
without reliable revision ordering need a documented reconciliation strategy.

Set per-source request, concurrency, time, byte and storage budgets. Reserve
capacity for current ingestion and API reads; backfills yield first under
pressure but remain resumable and visibly scheduled. Allocate budgets from
measurements, not a universal requests-per-minute number.

Prefer official bulk archives for history and supported APIs/feeds for changes.
Do not launch parallel crawlers that each assume they own the same API quota.
Use bounded retries with jitter, Retry-After handling, circuit breakers,
request deadlines and restart-safe leases.

Scheduling runs in a dedicated container worker built from the existing
backend code (2026-11-11), not a microservice rewrite. Next comes
PostgreSQL-backed work ownership/checkpoints. The API and worker must not both
schedule the same job. A broker, Redis, separate search engine or streaming
platform requires demonstrated need and a separate design decision.

Raw storage will outgrow transient staging. First measure growth and restore
cost, then choose versioned filesystem or object storage with hashes,
retention, access controls and off-site recovery. Do not put an unbounded
federal archive into either database-recovery directory by default. The
logical bundle is replaced daily and the pgBackRest repository is reserved
for PostgreSQL base backups and WAL.

## 7. Federal coverage map

The following is an initial domain catalog, not a claim that the listed
publishers provide every field or all history. Each source needs its own
access/rights/completeness assessment before implementation.

| Domain | Starting publishers/resources | Current and historical deliverable | Essential caution |
| --- | --- | --- | --- |
| Congress people and offices | Congress.gov; Bioguide; official House/Senate records; existing congress-legislators crosswalk | People, office terms, vacancies, party/chamber changes, committee assignments | Do not hardcode a permanently full membership count; distinguish seats, current officeholders and historical people. |
| Legislation and enacted law | Congress.gov; GovInfo; Office of the Law Revision Counsel | Bills/resolutions, amendments, actions, versions, cosponsors, public/private laws, statutory references | Source periods and document-version availability vary. Text versions and legislative actions are not interchangeable. |
| Votes and proceedings | House Clerk; Senate; Congress.gov/GovInfo as supported | Roll calls, member positions, journals/Record, associated measure and session | Preserve authoritative/fallback attribution, absences and unresolved historical IDs. |
| Committees and oversight | Congress.gov; official committee sites; GovInfo; GAO; CBO | Meetings, hearings, reports, testimony/document metadata, oversight outputs | Cancellations, revised agendas and attachment rights matter; publication may be delayed. |
| Nominations and treaties | Congress.gov; Senate; official executive records | Nomination/treaty lifecycle, office, actions and outcomes | Confirmed, appointed, sworn in and acting are different states. |
| Federal organization and leadership | SAM Federal Hierarchy; official agency directories; OPM PLUM; White House | Agencies, hierarchy, leadership terms, vacancies and reorganizations | Public SAM hierarchy access is not a complete deep org chart; CGAC mapping needs verification. |
| Executive and regulatory action | Federal Register; GovInfo; eCFR; Regulations.gov; official executive publications | Presidential documents, rules, proposed rules, notices, dockets, deadlines, regulatory versions | Publication, effective date and legal status differ; an executive order is not a bill-signing record. |
| Federal money | USAspending; Treasury Fiscal Data; OMB; authoritative budget/account publications | Awards/transactions, obligations/outlays, accounts, budgets, receipts and debt | Budget authority, obligations, outlays and award totals must not be added as though they are one measure. |
| Procurement and grants | SAM opportunities/awards interfaces; Grants.gov; USAspending | Solicitations, amendments, grant opportunities and award relationships | Opportunities are not awards; cancellations and agency identifiers need history. |
| Elections and campaign finance | FEC; official certified election sources where needed | Candidates, committees, cycles, filings, amendments, aggregate finance and permitted receipt detail | A filing amendment may supersede rather than add to a total. Contributor reuse restrictions need separate treatment. |
| Lobbying and ethics | LDA; official House/Senate disclosures; authorized judicial disclosure sources | Registrations, periodic/amended filings, clients/issues and permitted disclosure metadata | Reported lobbying is not proof of influence; some disclosure uses and redistribution are restricted. |
| Federal judiciary | Supreme Court and court sites; FJC; GovInfo court opinions; CourtListener/RECAP; PACER only if approved | Courts, judges/terms, published opinions/orders, docket metadata and authorized records | RECAP is not all PACER; Article III biographies do not cover every judge type; sealed material is excluded. |
| Accountability and administration | GAO; Inspectors General/Oversight.gov; official performance, FOIA and workforce publications | Reports, recommendations, status changes, aggregate workforce and administrative performance | Do not conflate audit findings with adjudicated misconduct; minimize personal data. |
| Geography and population context | Census APIs/TIGER/Geocoder; HUD crosswalk; official election boundary sources | Vintage-aware boundaries, demographic context, geographic joins and representation lookup | District definitions change; postal ZIP, ZCTA and electoral district are different concepts. |
| Government-wide dataset discovery | Data.gov; agency data.json/DCAT inventories; GovInfo catalog; publisher catalogs | Searchable metadata, access methods, formats, historical range, licensing and integration backlog | Catalog metadata is not the underlying dataset and can contain obsolete or unsafe distribution URLs. |
| Long-tail federal datasets | Agency statistical, scientific, environmental, transportation, health and other public catalogs | Catalog all discoverable public entries; integrate by declared relevance and readiness | No universal schema or blanket license; respect suppressed data, privacy, access controls and source-specific semantics. |

### First net-new federal source

After foundation gates, add Federal Register presidential-document/rule/notice
metadata as a bounded first executive slice, with an agency mapping and a
historical backfill. It adds cross-branch breadth without first requiring
full PACER access or an entire spending warehouse.

This choice still requires an access probe from the authorized dev environment:
the documentation fetch during planning encountered an automated-access
challenge. Do not bypass it. If access or terms block the source, record that
and evaluate the official GovInfo distribution before choosing another slice.

## 8. Execution waves and dependencies

Complexity is relative engineering risk, not a calendar estimate.
Each wave consists of small releases, not one enormous pull request.

| Wave | Complexity | Prerequisites | Scope and exit gate |
| --- | --- | --- | --- |
| R0: Reconcile and secure the baseline | Medium | Existing operational recovery baseline | Reconcile producer/test drift; green exact-SHA CI; source/deployment parity; no known broken regression expectation. |
| R1: Data integrity foundation | High | R0 | Source contracts, provenance, run/checkpoint model, destructive-write protection, concurrent-cache correctness, versioned IDs/terms. |
| R2: Reliable ingestion execution | High | R1 | Current/history lanes, isolated worker ownership, restart-safe progress, shared budgets, bounded resource use and recovery rehearsal. |
| F1: Federal legislative depth | High | R1; R2 before sustained backfills | Full declared current-Congress enumeration plus historical partitions; office terms, versions, votes, nominations and committee material. |
| F2: Executive organizations and action | High | R1-R2; entity-ID decision | Agency/leadership foundation and Federal Register vertical slice, then regulation/docket expansion. |
| F3: Money and accountability | High | Agency/CGAC foundation; R1-R2 | USAspending/Treasury, procurement/grants, FEC completeness, lobbying and permitted ethics data with reconciled financial semantics. |
| F4: Judicial coverage | High | R1-R2; judicial-ID and rights decisions | Courts/judges, official opinions, history, then eligible docket coverage with explicit access gaps. |
| F5: Connected federal activity and coverage closure | High | Relevant F1-F4 domains | Evidence-backed relationships, queryable timelines, catalog reconciliation and signed-off federal coverage report. |
| S1: State foundation and expansion | High | Accepted federal transition gate | Pilot jurisdictions, current/history parity, all three branches, coverage-driven expansion. |
| L1: Local foundation and expansion | High | State transition gate | Jurisdiction inventory, representative local pilots, platform adapters, geography and coverage evidence. |
| P1: Optional API/tenant product | High | Stable versioned contracts, rights audit, separate approval | A later product program; not automatically dependent on completing every local archive. |

F2-F4 research and fixture acquisition may overlap after R0; no team needs to
wait idly for unrelated branches. Production expansion depends on shared
foundation gates, resource capacity and the specific identifier model.
Federal catalog discovery begins in R1 and continues throughout, not after F4.

### R0: Baseline and code security

1. Compare exact source changes, regression tests, CI and deployed SHAs.
   Resolve the four producer/test discrepancies in section 3.
2. Review request validation/auth, outbound URL handling and redirects,
   proxy-header trust, payload limits, log redaction and frontend link schemes.
   Preserve existing UI behavior unless an intentional change is approved.
3. Review bill/donation cold-cache work: bound latency and capacity, serialize
   per-key mutations without holding DB locks across remote requests, and
   report partial/unavailable outcomes explicitly.
4. Scan locked Python/JavaScript dependencies and container images in CI.
   Pin reproducible releases/digests with an update process; pinning alone is
   not ongoing security maintenance.
5. Require protected release checks and no secrets in build arguments,
   published artifacts or fixtures. Review runtime versus build-time variable
   scope. Keep isolated environments and private service aliases.
6. Audit parser size/time/decompression bounds and migration safety.
   Prefer primary source APIs/bulk data to fragile scraping.

**Acceptance:** targeted regression tests demonstrate the original failures;
CI passes; security findings have explicit dispositions; dev data pages,
auth denial, readiness and source failure behavior work. No known high/critical
exploitable vulnerability proceeds without remediation. A static review is
not represented as a runtime penetration test.

**Status (2026-11-11): first pass and Phase A green in CI.**
See the R0 entries in the [build log](../CODE-MANIFEST.md). The first pass
(items 1–3, with regression tests) passed CI on `dev` and `main`. Under item 2,
trusted-proxy CIDRs remain deferred until the platform subnet is confirmed.
Phase A covers items 4 and 6:
- Item 4: images are pinned by digest and Actions by SHA. The backend installs
  and audits a hash-locked `requirements.txt` compiled in CI. `pip-audit` and
  a Grype image scan now sit alongside the npm audit gate, and Dependabot
  proposes bumps.
- Item 6: request bodies are capped. Every upstream response is read under a
  byte cap and a wall-clock deadline. XML entity declarations and YAML aliases
  are refused, and HTML reduction is linear-time. Migrations run with a lock
  timeout, and CI checks upgrade, drift, downgrade and re-upgrade against
  Postgres.

Under item 5, release deployment is still manual, not CI-gated. None of the R0
changes needed a migration. Phase A passed CI on `main` (merges of #12 and
#16) and is deployed to dev and production. On dev, `/health` reported the
released SHA and a scratch backup on the new image succeeded. The hash lock is
committed. Acceptance still requires the remaining dev-environment checks
above.

### R1: Correctness and provenance

Deliver a minimal source registry and persistent run/checkpoint history.
Use explicit contracts rather than building a universal connector framework
before several real sources need it.

Required source-run evidence:
source/partition, start/end, extractor version, outcome, expected/seen/accepted/
rejected counts, pages/cursors, bytes, watermark, errors, source provenance and
the published generation. Retain only non-secret error details.

Add protections for:

- Empty/full-replace snapshots, incomplete pagination and duplicate/repeated
  pages; preserve last good data and quarantine suspect material.
- Schema changes, missing IDs, duplicate source keys, out-of-order revisions
  and malformed dates. Use the shared normalization rules consistently.
- Donation-cache concurrency, counted versus actually inserted records, cursor
  advancement and rollback. Make duplicate requests and retries idempotent.
- Roster/committee/crosswalk consistency, historical person references,
  office/agency terms and boundary vintages.
- Last-success semantics: distinguish transport success from completeness
  without retroactively relabeling historical evidence as verified.

Shrink thresholds are source-specific and operator-approved after measuring
normal change. Do not choose an arbitrary universal percentage. Until a
source is understood, fail closed for destructive replacements and allow
review/replay rather than silent partial publication.

**Acceptance:** fixtures for empty, truncated, malformed, reordered and duplicate
input cannot silently reduce a complete live dataset. A run can be reproduced
from its retained lawful input and version metadata. Historical references
resolve or appear as explicit coverage gaps.

**Status (2026-11-11, Phase B):** delivered the source registry
(`app/sources.py`), `source_runs` history with per-source advisory locks and
staging-input hashes, `member_terms`, and guarded roster departures
(`members.in_office`). Not yet done: partition/cursor/watermark fields (they
arrive with the first fully enumerated source, queue item 4), retained raw
inputs for replay, shrink thresholds for the other sources, and historical
legislators.

### R2: Resilient execution

- Separate serving from ingestion ownership before materially increasing
  workload. Enable exactly one scheduler owner or use proven per-job leases.
- Checkpoint fetch and publish stages independently; completed work is not
  repeated indefinitely after restarts.
- Use time-window overlap plus deduplication for sources with late updates.
  Reconcile inventories periodically to catch missed windows and deletions.
- Budget current/history/public-request activity against the same source
  account limits. Cancellation must not free a quota slot while work continues.
- Quarantine poison records; expose an explicit bounded retry/replay process.
- Exercise out-of-space, partial download, network outage, database interruption,
  process termination and deployment overlap in isolated test.
- Measure database queries/indexes, pagination, connection pools and memory
  before adding caches or infrastructure.

**Acceptance:** killing a worker mid-partition then restarting it produces no
silent omissions, double-counted money, lost newer revisions or duplicate
concurrent ownership. Current-lane objectives hold while backfills run.
Capacity and restore measurements cover the next planned data slice.

**Status (2026-11-11, worker split):** scheduled refreshes run in a separate
`worker` service on the deployment platform, the only scheduler owner there.
It starts only once the database is at its image's migration head, exposes a
heartbeat health check, and records refreshes cancelled at shutdown as
`abandoned`, and its latest staging snapshots persist across redeploys. The
worker release was verified at `bf735b4`.

**Shared budgets (implemented; CI/dev acceptance pending):** migration 0015
coordinates rolling-hour reservations across API, worker and manual processes
in the same database. Separate API/worker shares and a common source ceiling
survive restarts; uncertain admission fails closed. The initial migration has
an approved one-hour upstream hold; stop old processes before applying it.
Not yet done: stage checkpoints, replay/quarantine, retained versioned raw
input, and the broader failure exercises above. Cross-environment accounting
is not provided; dev must use separate source credentials.

### F1-F4: Vertical slices, not disconnected scrapers

Every source increment delivers:

1. Access/rights decision and coverage inventory.
2. Fixtures and typed raw-shape validation.
3. Current discovery and resumable historical enumeration.
4. Normalization/identity decisions and reviewed additive migrations.
5. Transactional publication with provenance and run evidence.
6. Bounded API queries, source links and explicit partial/freshness indicators.
7. A useful UI path and accessibility checks where the source is user-facing.
8. Failure, reconciliation, performance and restore evidence.

Prioritize one useful slice per release: for example official presidential
documents and source links before an entire executive dashboard, or court
opinions before every possible docket attachment. Full available history
starts with each source, but source-specific backlog progress remains visible.

### F5: Cross-branch relationships and federal closure

Use typed relationships with the supporting record/citation, not a generic
"related" label that implies causation:

- Bill -> legislative action -> enacted public/private law.
- Law/statutory authority -> rule or agency action, where cited.
- Rule/law/action -> judicial opinion or docket, only with supporting evidence.
- Appropriation/account -> obligation/outlay/award where documented identifiers
  permit it; do not imply every award has a unique bill-level link.
- Official -> office/agency/committee during a specific term.

Court citations are often many-to-many and do not by themselves establish that
a case challenged a law. An executive order is not the signature stage of a
bill. The UI must preserve these distinctions.

Build a factual activity stream from verified records and revisions. It need
not use WebSockets to be near real time; polling/conditional requests may
suffice. No inferred legal conclusions, political scores or AI summaries.

**Acceptance:** every displayed relationship has evidence, every domain has a
coverage disposition, and a sampled change can be traced through source ->
raw/versioned record -> normalized entity -> API -> UI. The operator approves
the federal transition report, including open history and catalog gaps.

## 9. State expansion

Begin only after the federal transition gate. Select a small representative
pilot set by access quality and structural diversity, not personal preference:
different legislative systems, court publication practices, finance sources
and geography. Select the actual jurisdictions in a separate approval.

Use authoritative state publishers as the reference; evaluate Open States and
other aggregators as documented distributions/crosswalks, not substitutes for
source provenance.

For each state cover legislative members/terms, bills/actions/text/versions,
votes, committees, governor/executive action, agencies, spending/procurement,
elections/finance, courts/opinions and jurisdiction geography as accessible.
OCD identity and state-local statutory/organizational differences are first-class.

Run current and historical lanes together. Admit each additional jurisdiction
through the same source checklist. Publish a state-by-domain coverage matrix;
"50 states" without domain/history evidence is not a completion claim.
Track DC, territories and other jurisdictions explicitly rather than quietly
including or excluding them under a state count.

**Local transition gate:** representative state adapters are reusable, all
states/territories in the approved inventory have an assessed disposition,
implemented coverage passes reconciliation, and the operator accepts the
remaining gaps. Do not let a single inaccessible archive lead to fabricated
coverage or an unapproved permanent delay.

## 10. Local expansion

First inventory counties, municipalities, special districts and other approved
local bodies using authoritative jurisdiction data and geographic vintages.
Handle consolidations, overlapping jurisdictions and name changes.

Pilot a city, county and another structurally different local body where lawful
data access exists. Then build adapters around proven source families:
Legistar and other official legislative portals, budgets/procurement systems,
published ordinances/codes and official court sources.

Source-vendor presence does not establish universal coverage or bulk reuse
permission. Start read-only; do not call government write/comment APIs.
Treat PDFs, scanned agendas and OCR as evidence with extraction quality and
human-readable originals, not automatically verified structured facts.

Deliver officials/terms, meetings/agendas/minutes, legislation/votes, budgets,
spending and jurisdiction lookup incrementally. Every jurisdiction has a visible
coverage and freshness report. Historical data is partitioned by jurisdiction
and period, not hidden behind a global progress percentage.

Tribal governments are sovereign jurisdictions, not a generic county/local
subtype. Any inclusion requires its own scope, authority and data-governance
decision.

## 11. Cataloging all discoverable federal datasets

Use Data.gov metadata, publisher inventories and official branch catalogs to
maintain a living registry. Record at least:

- Publisher, branch/domain, jurisdiction and stable catalog/source identifier.
- Title/description, source and distribution URLs, formats and access methods.
- Temporal/geographic scope, earliest/latest known availability, revision cadence.
- Public/restricted status, terms/license, attribution, commercial reuse and
  bulk redistribution decision; date those terms were reviewed.
- Approximate size, rate/access limits, account requirements and estimated cost.
- Integration state, completeness definition, backfill partitions and blockers.
- Authoritative versus third-party distribution, replacement/mirror relationships.

Deduplicate metadata without collapsing distinct vintages or revisions.
Record disappeared entries and changed URLs; do not silently delete their
history. Reconcile inventories periodically and publish denominator changes.

**Catalog discovery never automatically executes arbitrary distribution URLs.**
Validate schemes, hosts and redirects; reject private/link-local/metadata
targets; enforce egress, size, archive and content-type bounds. Source onboarding
must prevent SSRF, unsafe archive extraction and unbounded downloads.

Prioritize deep ingestion by public value, authoritative quality, availability,
reuse rights and cost. Dataset count alone is not the product's success metric.

## 12. Security, privacy and future business compatibility

Open-source software licensing is separate from rights in government data,
third-party collections, attachments and personal information.

- Preserve the current code license; a future commercial offering does not
  silently change it or source rights.
- Track per-dataset permissions for display, export, redistribution and paid
  API access. Unknown rights mean "not approved", not "public domain".
- FEC individual-contributor information has sale/use restrictions, including
  commercial-purpose and solicitation restrictions. Do not include it in a
  paid data product based only on API accessibility. Obtain a qualified
  dataset/use-specific determination before monetization.
- Review disclosure-record restrictions, court redactions and third-party
  licenses. Retain revision provenance without making restricted or removed
  personal information permanently redistributable.
- Minimize personal data not necessary for government accountability. Exclude
  sealed/restricted records; support correction and source-removal review.
- No bypassing authentication, bot controls, quotas or fee systems. Approved
  paid sources need a budget ceiling and separately authorized acquisition.
- Keep credentials runtime-scoped where possible, use least-privilege
  migration/ingestion/API roles when implemented, and test environment isolation.
- Incrementally enforce CSP/link safety, dependency/image scanning, safe
  logging, input/output limits and query budgets with regression tests.

A monitor colocated with production may observe containers but cannot by itself
prove that its own host/network is reachable. If monitoring is later resumed,
design that failure domain explicitly. No monitoring infrastructure is added now.

### Later API/tenant offering

Prepare compatibility through stable IDs, versioned response contracts,
cursor pagination, provenance and documented coverage now. Do not scaffold
accounts merely because they might be useful later.

The separately approved product phase must cover API keys, tenant isolation,
roles/seats, quotas, usage accounting, billing, audit logs, revocation,
export entitlements, abuse handling, privacy and support obligations. Public
data is not automatically a tenant secret; tenant annotations, credentials and
usage data are. Test cross-tenant access failures and rights-aware exports before
any paid launch. Price or promise freshness only after sustained measurement.

## 13. Release and validation contract

For every increment:

1. Define scope, invariants, acceptance measurements, risks and rollback first.
2. Add deterministic tests for both success and the actual failure cases.
3. Run focused and integration checks in CI, not this static local checkout.
4. Review the diff for security/data correctness and require green CI for the
   exact commit.
5. Deploy to isolated dev; keep production credentials/logs out of test, and
   enable only explicitly authorized dev ingestion tasks.
6. Reconcile representative source partitions and verify UI/API behavior.
7. Promote to main through review, record the deployment SHA, check readiness
   and source-run evidence, and keep a rollback path.
8. Update the build log and source coverage record with observed results,
   not merely implementation claims.

Test matrix:

| Area | Required examples |
| --- | --- |
| Input/security | Malformed IDs/payloads, unauthorized/internal access, spoofed proxy headers, unsafe URLs/redirects, bounded bodies and secret-free failures. |
| Ingestion | 429/5xx/timeouts, page loops/caps, empty and truncated snapshots, duplicate/malformed records, schema drift and missing identifiers. |
| Data integrity | Amendment/retraction semantics, late updates, history/current races, crosswalk conflicts, money reconciliation and transactional rollback. |
| Recovery | Worker termination, lease expiry, resume from committed checkpoint, replay from retained input and restore of each newly persisted storage type. |
| Product | Honest missing/partial states, source links, dates/timezones, accessibility, large-list pagination and stale/fallback attribution. |
| Performance | Recorded corpus size, concurrency, p95 latency, DB connections, memory/disk growth and source quota use under current plus backfill load. |

Use expand/backfill/validate/contract migrations. Keep old readers compatible
until backfills and new readers are verified. No automatic destructive
downgrade is a rollback strategy. A source may be disabled while preserving
last-good data and exposing its stale state.

Resource planning accompanies each slice: expected rows/year, average record/
attachment size, indexes, request budget, full backfill duration, recurring
storage growth, backup duration and measured restore time. Do not authorize
an unbounded all-history download without this estimate.

Backups remain a working foundation, not a completed-forever task. New raw
archives, worker state, source registry and history stores must enter the
recovery inventory. PostgreSQL now has a local pgBackRest WAL archive and
daily full backups with seven-day retention; the daily logical dump remains an
independent fallback. Duplicati copies both directories to two off-site
destinations. Local PITR depends on continuous archive health, and off-site
PITR depends on the latest complete Duplicati repository copy. Both still
require a rehearsed restore and measured storage/restore times.

## 14. Immediate work queue

Execute these before promising additional production coverage:

| Order | Work item | Evidence required to close |
| --- | --- | --- |
| 1 | Reconcile the current hardening producers/tests and exact CI baseline. | Tests and code agree; green release SHA and documented deployment status. |
| 2 | Finish the focused code review: donation concurrency, safe source parsing, migration safety, URL handling and dependencies. | Ranked findings, reproductions, fixes or explicit accepted deferrals; no hidden severe blocker. |
| 3 | Define source-run/provenance and office-term/history contracts with additive migrations. | Approved models, migration/replay tests, unresolved identity policy. |
| 4 | Make one existing source fully enumerated and restart-resumable in current and historical lanes. | Reconciled partition counts, interrupted-run recovery, no stale overwrite. Prefer legislative bills/votes as the first proof. |
| 5 | Introduce worker ownership/budgets when sustained backfill starts. Worker split released; shared PostgreSQL ledger implemented, awaiting CI/dev acceptance. | No duplicate scheduler, quotas honored, API capacity preserved. |
| 6 | Build the initial federal catalog and source rights/access register. | All section 7 domains assessed; candidate sources have real evidence, not assumed licenses. |
| 7 | Deliver the first executive vertical slice and its history. | Federal Register/GovInfo access decision, agency identity, source links, CI and dev reconciliation. |

Items 3 and 6 can overlap after baseline reconciliation. A source's schema
must not be implemented before its identity, rights and completion rules are
decided. Do not block unrelated safe work on an inaccessible source.

No fixed delivery dates are committed. Establish estimates after the first
measured full-source backfill and resource profile, then forecast each domain
using its actual volume, source behavior and available engineering capacity.

## 15. Source references and verification limits

Publisher documentation consulted during this planning pass; API operation,
credentials, quotas and rights still require onboarding verification:

- [Data.gov APIs](https://data.gov/developers/apis/): catalog APIs describe
  datasets; they do not themselves contain the underlying records.
- [Congress.gov API](https://api.congress.gov/): source entry point; enumerate
  actual endpoint/history support during F1.
- [GovInfo developer hub](https://www.govinfo.gov/developers): APIs, bulk data,
  RSS/sitemaps and the legislative branch catalog.
- [Federal Register API documentation](https://www.federalregister.gov/developers/documentation/api/v1):
  automated-access challenge encountered during this pass; successful API
  access is not claimed.
- [SAM Federal Hierarchy public API](https://open.gsa.gov/api/fh-public-api/):
  documented public hierarchy depth and role-dependent quotas constrain design;
  confirm account-specific limits before scheduling.
- [Regulations.gov API](https://open.gsa.gov/api/regulationsgov/):
  read-only discovery first; public comment submission is not part of this plan.
- [USAspending API](https://api.usaspending.gov/docs/) and
  [Treasury Fiscal Data API](https://fiscaldata.treasury.gov/api-documentation/):
  distinct financial datasets and semantics.
- [LDA downloads](https://lda.gov/api/): LD-1/LD-2 and LD-203 records;
  confirm the actual machine-readable interface before implementing a client.
- [FEC contributor-use guidance](https://www.fec.gov/updates/sale-or-use-contributor-information/):
  commercial/solicitation restrictions are a material future-product constraint.
- [Federal Judicial Center biographies](https://www.fjc.gov/history/judges):
  historical judicial coverage has explicit court/appointment boundaries.
- [CourtListener data services](https://www.courtlistener.com/help/api/):
  REST, bulk and other delivery options have separate access arrangements.
- [PACER fees](https://pacer.uscourts.gov/pacer-pricing-how-fees-work):
  access is not uniformly free; searches and records can incur fees.
- [Census developer resources](https://www.census.gov/data/developers.html):
  dataset discovery, APIs and geographic identifiers.
- [Open States API documentation](https://v3.openstates.org/docs):
  assess source and jurisdiction coverage before state onboarding.
- [Legistar API documentation](https://webapi.legistar.com/Help):
  per-client resources; use read-only operations and verify jurisdiction access.

Publisher pages are evidence of documented interfaces, not guarantees of
availability, completeness, legal reuse or a future service level.
