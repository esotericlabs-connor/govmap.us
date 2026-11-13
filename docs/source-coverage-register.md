# Source and coverage register

Initial static inventory: 2026-11-12. This is the first Group 2 deliverable,
not a claim that existing API access is exhausted or that new datasets are live.
It describes checked-in behavior and public publisher documentation, not account
entitlements, deployed configuration, database counts or legal clearance.

## Reading the register

- **Delivered-partial**: the code serves a bounded subset; completeness is not verified.
- **Queued**: a useful expansion, not implemented. Uninspected fields stay queued.
- **Duplicate**: preserve publisher/version provenance rather than double-count records.
- **Privacy-restricted**: publication/use review is required before expansion.
- **Deferred**: an explicit reason prevents work in the current sequence.

The runtime [source registry](../backend/app/sources.py) lists refresh jobs.
It is not an endpoint inventory: lazy bill enrichment, committee referrals and
donations also call upstream services. Its `rights=None` values remain unchanged;
this register does not turn a publisher's public endpoint into a blanket license.

## Access, quotas and rights

| Publisher/access | Checked-in credential configuration | Published limit versus application budget | Rights and open gates |
| --- | --- | --- | --- |
| [Congress.gov](https://github.com/LibraryOfCongress/api.congress.gov) | `CONGRESS_GOV_API_KEY` | Docs: 5,000 requests/hour, at most 250 rows/page. Default application total: 4,500/hour. | Cite Congress.gov and retain original records. Verify document-specific rights for attachments; actual account limit and remaining quota are unverified. |
| [OpenFEC](https://api.open.fec.gov/developers/) | `FEC_API_KEY` | Docs: standard 1,000/hour, 100 rows/page; higher access requires approval. Default application total: 900/hour. | [Individual-contributor restrictions](https://www.fec.gov/updates/sale-or-use-contributor-information/) prohibit solicitation and commercial use; public availability is not permission for every use. Rankings and exports require a use review. |
| [HUD USPS crosswalk](https://www.huduser.gov/portal/dataset/uspszip-api.html) | `HUD_API_TOKEN` | Code requests 5,000 rows/page, bounded to 60 pages. This is not a publisher quota. | Public documentation did not render during this review. Account quota, permitted redistribution and release metadata remain unverified; do not expand access assumptions. |
| [congress-legislators](https://github.com/unitedstates/congress-legislators) | None | Public files; no application-wide hourly budget for these downloads. | Community-maintained data, not an official government publisher. Record upstream revision and review repository/source terms before historical expansion. |
| House Clerk / Senate LIS / Voteview | None | Code limits recent votes per chamber; body limits and fallback refetch interval are not publisher quotas. | Keep official feeds distinguishable from the academic Voteview fallback; fallback success must not certify official-feed freshness. |
| [GovInfo API](https://github.com/usgpo/api) | No dedicated API key setting or API client; current text retrieval uses public document URLs | Current docs: 36,000/hour, 1,200/minute, 40/second. Application `govinfo` download budget defaults to 600/hour; that does not prove API access. | Docs support an existing api.data.gov key. Validate the intended credential privately before integration; never assume Congress and FEC keys are identical. [GPO policy](https://www.govinfo.gov/about/policies) warns that publications may contain third-party copyrighted material. |
| LDA | No configured credential or ingestion module found in this inventory | Unverified | Deferred pending endpoint/access and rights verification. Roadmap mention is not an integration. |

Application budgets come from [config](../backend/app/config.py), with durable
shared admission in [upstream](../backend/app/services/upstream.py). Deployment
overrides and shared-key consumers are unknown here. New jobs must use those
budgets and the existing worker; no quota increases, paid services or extra
infrastructure are authorized by this document.

## What existing ingestion actually retains

| Path and disposition | Retained identity/fields | Limits and missing coverage | Next normalized data/use |
| --- | --- | --- | --- |
| Current roster, committees, memberships: **delivered-partial** | Bioguide, crosswalk arrays, names, current office/party/contact, parsed terms, committee relationships | Only current roster files are fetched. Current people may carry prior terms, but this is not a historical-member corpus. Extra fields are ignored by raw schemas. | Preserve all evidenced office terms and source revision before elections/transition views; do not equate candidate registration with service. |
| Recent bills: **delivered-partial** | Congress/type/number, title, sponsor Bioguide, introduced/update/latest-action dates, policy area, enacted flag, action text/type/chamber, cosponsors, latest CRS summary and text URL/version | Default 250 most recently updated measures/run. Subresources stop at 20 pages; invalid child rows can be skipped. Neither proves a complete action log. | Fail/label incomplete subresources before replacement; durable overlapping update windows and reconciliation counts. |
| Bill field loss: **queued** | `laws` supplies only the enacted flag; action `sourceSystem.name` becomes chamber | Law type/number are not stored; action code/time, original source code/name, recorded vote links and text/summary version history are not retained. `updateDate` loses time precision. | Add law identifiers, action provenance and source timestamp precision. Retain version history and link typed votes rather than deriving all stages from text forever. |
| Sponsored legislation: **delivered-partial** | Sponsor Bioguide and bill stubs from `member/{id}/sponsored-legislation` | Four pages/member; current members only. Enrichment backfill selects never-enriched stubs, not stale enriched rows. | Resumable member/history cursors and bounded correction refresh. Older/newly published CRS summaries need rechecks, not AI replacements. |
| Bill document cache: **delivered-partial**, alternate publisher metadata **duplicate** | Latest readable text, source URL/version and revision-aware cache | Lazy first request; up to 16 MiB upstream HTML. Not all document versions or a full GovInfo API integration. | Preserve source version/date/checksum and reviewed formats; avoid downloading PDF/XML/HTML copies indiscriminately. |
| Committee meetings/referrals: **delivered-partial** | Event ID, chamber, time/status/title/location, committee codes and related bills; lazy referred-bill list | Default 300 recent meetings/chamber; referrals default to 15. Witnesses, video, support documents and related nominations/treaties are outside modeled fields. | Expand typed relationships and documents with page completeness and distinct scheduled versus actually held events. |
| Roll calls: **delivered-partial** | Chamber/Congress/session/roll, date, question/result, totals and member positions mapped through Bioguide | Default latest 100/chamber; older rows on file do not imply full history. House/LIS parsing and Voteview fallback have different coverage. | Reconcile chamber inventories by session; refresh corrected votes and retain publisher/revision for each record. |
| Member finance totals: **delivered-partial** | Receipts, spending, cash/debt, contribution categories, transfers/loans/refunds, coverage dates and cycle | First matching-office FEC ID is selected from the array; newest cycle with activity is preferred. Existing amounts use floating point. Not all candidate IDs, races, committees or historical cycles. | Reconcile all evidenced IDs and verify read-adapter parity before replacing the member card; never silently sum overlapping totals. |
| FEC candidate financial summaries and linkage: **delivered-partial** | Candidate FEC ID, reported office/state/district and party, exact-decimal gross summaries, coverage end, source linkage IDs/years and committee IDs; archive hashes, optional modification times and fetch time | Configured two-year file only; one summary per candidate who raised or spent money, not all registrations. Some publisher-reported linkage years fall outside 1900–2100 and are flagged as unverified. No claim that every publisher record has been independently reconciled; authorized-committee transfers can double-count activity and financial periods can differ. Source-reported candidate districts are not a FIPS/boundary-vintage geographic join. Committee IDs are linkage evidence, not committee totals. | Reconcile multiple candidate IDs, committee coverage and comparable filing periods. Add donor geography and organization or individual rankings only after lineage and use review; keep independent spending separate. |
| Itemized receipts: **delivered-partial / privacy-restricted** | `sub_id`, committee, amount/date, contributor name, city/state, employer/occupation, year-to-date aggregate | One selected principal committee; first 20 committee results; Schedule A fetched in at most eight pages/request, with persistent keyset cursor. Cached subset and reported total are distinct. | Audit amendment/back-reference/transaction IDs, memo entries, conduit/earmark and entity fields before rankings. Current display-field schema cannot support deduplicated money-flow analysis. |
| ZIP to district: **delivered-partial** | ZIP and state/district pairs; all parsed pairings, not a claimed single exact district | Parser discards source GEOID after decoding, ratios and release vintage; current table replacement has a size guard, not version reconciliation. | Preserve FIPS/GEOID, Congress/boundary vintage and ratios through shared normalization. Quantify ambiguous ZIPs; never use ZIP as exact residence/donor district. |

Implementation evidence:
[raw bill schemas](../backend/app/schemas/bill.py),
[bill pipeline](../backend/app/pipelines/congress_gov_bills.py),
[bill normalization](../backend/app/normalize/bills.py),
[lazy enrichment](../backend/app/services/bill_enrich.py),
[sponsored pipeline](../backend/app/pipelines/congress_member_sponsored.py),
[member schema](../backend/app/schemas/member.py),
[committee schema](../backend/app/schemas/committee.py),
[finance schema](../backend/app/schemas/finance.py),
[finance pipeline](../backend/app/pipelines/fec_finance.py),
[candidate-finance bulk pipeline](../backend/app/pipelines/fec_candidate_totals.py),
[candidate-finance normalization](../backend/app/normalize/campaign_money.py),
[election candidate schema](../backend/app/schemas/election.py),
[election candidate pipeline](../backend/app/pipelines/fec_candidates.py),
[donation service](../backend/app/services/donations.py),
[HUD parser](../backend/app/pipelines/zip_crosswalk.py).
Staging is often the validated, reduced shape, not a lossless raw archive;
discarded fields cannot be recovered without refetching.

## Congress.gov endpoint-family dispositions

Checked against the publisher's [OpenAPI document](https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/openapi.json)
and [endpoint documentation](https://github.com/LibraryOfCongress/api.congress.gov/tree/main/Documentation).
Each row includes its list/detail/filter variants. Parameters are abbreviated;
use the publisher contract, not this table, to construct requests.

| Family and child resources | Disposition and purpose |
| --- | --- |
| `bill`, actions, cosponsors, summaries, text | **Delivered-partial** as above. Refresh/completeness comes before increasing caps. |
| Bill amendments, committees, relatedbills, subjects, titles | **Queued**: stable links and title/subject provenance for the legislative workspace. Additional fields require raw-schema review. |
| `law` by Congress/type/number | **Queued**: preserve the law identifier and originating bill link. **Duplicate** bill objects must not inflate enacted counts. |
| `amendment`, actions, cosponsors, nested amendments, text | **Queued**: source amendment identifiers and links, including amendments to amendments. |
| `summaries` aggregate feed | **Queued**: changed CRS summaries and history; **duplicate** content relative to bill summaries. Not standalone AI-written summaries. |
| `congress`, `congress/current` | **Queued**: official Congress/session dates and transition checks, not proof of individual officeholders. |
| `member`, by Congress/state/district; sponsored-legislation | Sponsored subset **delivered-partial**; other variants **queued** for identity/history comparison with the roster. |
| Member cosponsored-legislation | **Queued**: cross-check complete cosponsorship history through Bioguide. |
| `house-vote`, member positions | **Queued** parity comparison with Clerk roll calls; **duplicate**, not a replacement feed until identifiers/results/coverage agree. |
| `committee`, bills, reports, nominations, house-/senate-communication | Bill referrals **delivered-partial**; remaining official metadata and relationships **queued**. Verify deployed API route variants against the contract. |
| `committee-report`, text | **Queued** with report/session/part metadata; compare GovInfo copies. |
| `committee-print`, text; `hearing` | **Queued** with jacket/document identifiers and publisher version, not title matching. |
| `committee-meeting` | **Delivered-partial**; additional fields/documents **queued** as above. |
| `congressional-record`, `daily-congressional-record`, articles, `bound-congressional-record` | **Queued**; reconcile editions and GovInfo granules. Large text acquisition waits for measured storage and publication rights. |
| `house-communication`, `senate-communication` | **Queued** for agency-to-Congress oversight links; retain source identifiers and dates. |
| `house-requirement`, matching-communications | **Queued**: required reports and evidenced fulfillment, not an inference of misconduct from missing data. |
| `nomination`, nominees by ordinal, actions, committees, hearings | **Queued** for Executive/Judicial. Nominee identity is not automatically a legislative person/Bioguide record. |
| `crsreport` | **Queued** as a distinct report corpus; not interchangeable with bill summaries. |
| `treaty`, suffix variants, actions, committees | **Queued** for source-grounded Senate/Executive activity. |

Historical ranges vary by collection and field: consult
[coverage dates](https://www.congress.gov/help/coverage-dates), then reconcile the
selected range. Pre-modern bill-number and introduced-date caveats in the
[bill documentation](https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/BillEndpoint.md)
make an unrestricted backfill **deferred** until identity/date handling is reviewed.

## Other access: endpoint/collection dispositions

| Source/family | Disposition and next use |
| --- | --- |
| OpenFEC `candidate`, `candidates`, `committee`, `committees` | Current member totals and candidate catalog **delivered-partial**; the on-demand member ledger resolves one principal committee. The catalog is cycle-scoped and grouped only by FEC-reported office/state/district. The candidate-list schema does not document principal committees, so an empty passthrough array is not evidence that none exist. Verified ballot access, committee history and broader race metadata remain **queued**. Keep FEC IDs as external candidate identities until an evidenced Bioguide mapping exists. No fabricated member IDs. |
| OpenFEC `schedules` | Schedule A subset **delivered-partial / privacy-restricted**. Receipt aggregates and other schedules **queued** for reconciliation of spending, debts, loans and independent expenditures; field/line-item semantics must be reviewed per endpoint. |
| OpenFEC `reports`, `filings`, `efile` | **Queued**: filed/amended/latest distinctions and lineage. Electronic filings are not automatically equivalent to processed reports. |
| OpenFEC `calendar-dates` (Election Dates category) | FEC-published calendar events **delivered-partial**, refreshed daily for the configured FEC cycle year. The category includes elections, runoffs, and party conventions. Timed event timestamps are displayed as publisher-local dates, and exclusive all-day ends become inclusive dates. Older end dates are withheld until a successful updated refresh. Exact pagination counts and event IDs are retained; entries can be revised and are not proof of state ballot qualification, official results, or a complete state/local calendar. FEC event IDs are not permanent; they identify records within a fetched snapshot, not durable event identities. The API has no event revision token; matching counts cannot prove the source was unchanged during pagination. GovMap stores a local content hash and fetch time. |
| OpenFEC `elections`, `election-dates`, `state-election-office`, `reporting-dates` | **Queued**: broader race catalog and official state-source discovery. These are not nationwide live election results or proof of ballot qualification. |
| OpenFEC `communication_costs`, `electioneering`, `presidential`, `national_party`, `totals` | **Queued**: separately labeled money datasets; never conflate spending for/against a candidate with contributions received by that candidate. |
| OpenFEC `audit-case`, `audit-category`, `audit-primary-category`, `legal`, `rulemaking` | **Deferred** to an evidenced accountability/regulatory slice; source classifications and outcomes need review, not automatic misconduct labels. |
| OpenFEC `names`, `rad-analyst`, `operations-log` | **Deferred** support metadata; no current user-facing need. Donor identities must not enter universal search. |
| FEC all-candidates and candidate–committee bulk files | **Delivered-partial** for the configured current finance cycle. Archive SHA-256 and a local parsed-content hash identify what was fetched; neither is an FEC revision ID nor proof of full upstream coverage. Latest reported dates must be compared explicitly, and authorized-committee transfers can double-count gross receipts and disbursements. Historical reconciliation and other bulk collections remain **queued**; never add API and bulk copies of the same activity. |
| congress-legislators historical people/committees, official social media, district offices | **Queued**: all published files not currently ingested. Preserve revision and historical terms; offices are not residential addresses. |
| congress-legislators `executive` | **Queued** President/VP reference; not a Cabinet roster. Document non-Bioguide identities and manual matches before adding a person pipeline. |
| HUD other crosswalk types/history/ratios | **Queued** after documentation/access review. No guessed type codes or 120th-Congress boundary assumptions. |
| GovInfo search, collections (modified-time windows), published, related | **Queued** discovery with cursor checkpoints. Enumerate actual collections/ranges after authenticated access is verified. |
| GovInfo package/granule summaries and content | **Queued** retrieval with publisher IDs, rendition/version and modified versus published dates kept distinct. |
| GovInfo BILLS/PLAW/STATUTE, CHRG/CRPT/CPRT/CDOC, CREC/CRECB | **Queued / duplicate** legislative publications; retain editions and canonical links across Congress.gov. |
| GovInfo presidential documents, FR/CFR, USCOURTS, BUDGET/GOVMAN | **Queued** Executive/Judicial slices. Verify collection codes and per-court/date coverage from live metadata; USCOURTS is not every federal docket/opinion. |
| GovInfo remaining collections | **Deferred** until discovery records the current inventory and demand. Publisher sample collection lists are examples, not current coverage proof. |

OpenFEC families were enumerated from its [Swagger schema](https://api.open.fec.gov/swagger/).
These family decisions do not certify every available field: unmodeled schemas,
account-only responses and collection histories remain explicitly queued.

The FEC describes its Schedule E candidate aggregates as excluding memoed
items, and its API documentation says candidate aggregates exclude 24/48-hour
reports to avoid double counting. `election_full` defaults to an election
period, not necessarily a two-year finance cycle. These observations are
preliminary source qualification, not evidence that amendments, report
revisions, periods or all outside spending have been reconciled. Schedule E is
not yet ingested or combined with campaign receipts.

The [FEC's contributor-use guidance](https://www.fec.gov/updates/sale-or-use-contributor-information/)
restricts using individual contributor information for solicitation, including
charitable solicitation, or commercial purposes. The existing on-demand
one-committee receipt cache is not an amendment-safe contribution census. The
existing ledger and its API also need review; their current availability does
not establish that their use is permitted. Expanded individual-donor views,
rankings or exports remain blocked pending a documented permitted-use review
of the donation-funded site and all relevant API and fundraising surfaces; a
public-source attribution alone is insufficient.

## Identity, dates and resource gates

Before each expansion:

1. Preserve Bioguide for federal legislative people, OCD for state/local,
   FIPS for geography and CGAC on both agency and spending records. Store FEC
   candidate IDs as an array; CRP and NAICS remain separate taxonomies.
   Document unsupported/missing mappings before writing an adapter.
2. Use shared `normalize_date()` at the normalization boundary, retaining source
   precision. Existing source-specific date coercions are reconciliation work,
   not a pattern to copy. Unknown day/month must not become an invented date.
3. Record publisher URL, retrieval time, source update/revision, requested range,
   pages expected/fetched, invalid/skipped rows and reconciliation outcome.
   A fresh run timestamp alone does not certify coverage.
4. Measure representative raw/normalized bytes, rows and requests per entity,
   including indexes, document history, WAL and retained backups. Numeric growth
   estimates are **unmeasured**, not zero. Start metadata-first and bound bodies,
   time, pages and concurrency; no unbounded document crawl.
5. Keep source-specific acquisition, validated staging, normalization and bounded
   API/UI separate. Additive migrations, correction replay and run/checkpoint
   evidence must ship with each new source.

## Next data-foundation slice

The next implementation should close existing acquisition gaps before widening
ingestion:

1. Make exhausted bill subresource pagination and rejected child rows explicit;
   never replace a complete action/cosponsor set with an unmarked partial set.
2. Design durable, overlapping update checkpoints and bounded stale-detail
   refresh so late corrections and newly published CRS summaries are revisited.
3. Expose measured coverage independently of freshness, with API contracts and
   regression fixtures for caps, interrupted runs, correction replay and restart.

This register makes those priorities concrete. Elections/transition, legislative
depth, Money, Accountability, Executive and Judicial remain subsequent vertical
slices; this change neither adds those pipelines nor changes production settings.
