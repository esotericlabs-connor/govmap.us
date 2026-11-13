import Link from "next/link";

import { CandidateMemberLink } from "@/components/CandidateMemberLink";
import { ChartFigure } from "@/components/dashboard/ChartFigure";
import { DataState, FreshnessBadge } from "@/components/dashboard/DataState";
import { Metric, Panel } from "@/components/dashboard/Panel";
import { formatDate } from "@/components/DetailKit";
import { PageBanner } from "@/components/PageBanner";
import { ListToolbar } from "@/components/ListToolbar";
import { ListPageLink } from "@/components/ListPageLink";
import { apiGet, HttpError } from "@/lib/api";
import type { CampaignMoneyCandidate, CampaignMoneyDetail } from "@/lib/campaign-money";
import { classifyFreshness, parseFreshnessReferenceTime } from "@/lib/freshness.mjs";
import { formatMeetingTime } from "@/lib/format";
import { formatMoneyExact, maxPositiveMoney, moneyCents, moneyPercent } from "@/lib/money.mjs";
import { moneyReturnHref, safeMoneyReturn } from "@/lib/money-navigation.mjs";
import { readListQuery } from "@/lib/list-controls.mjs";

export const dynamic = "force-dynamic";
export const metadata = { title: "Candidate campaign finance" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type AmountKey =
  | "receipts"
  | "disbursements"
  | "cash_beginning"
  | "cash_on_hand"
  | "debts"
  | "individual_contributions"
  | "other_committee_contributions"
  | "party_contributions"
  | "candidate_contributions"
  | "candidate_loans"
  | "other_loans"
  | "candidate_loan_repayments"
  | "other_loan_repayments"
  | "transfers_from_authorized"
  | "transfers_to_authorized"
  | "individual_refunds"
  | "committee_refunds";

const AMOUNTS: { key: AmountKey; label: string }[] = [
  { key: "individual_contributions", label: "Individual contributions" },
  { key: "other_committee_contributions", label: "Other political committee contributions" },
  { key: "party_contributions", label: "Party committee contributions" },
  { key: "candidate_contributions", label: "Candidate contributions" },
  { key: "candidate_loans", label: "Loans from candidate" },
  { key: "other_loans", label: "Other loans" },
  { key: "transfers_from_authorized", label: "Transfers from authorized committees" },
  { key: "transfers_to_authorized", label: "Transfers to authorized committees" },
  { key: "candidate_loan_repayments", label: "Candidate loan repayments" },
  { key: "other_loan_repayments", label: "Other loan repayments" },
  { key: "individual_refunds", label: "Refunds to individuals" },
  { key: "committee_refunds", label: "Refunds to committees" },
  { key: "cash_beginning", label: "Cash at beginning of period" },
];

const INFLOW_FIELDS = new Set<AmountKey>([
  "individual_contributions",
  "other_committee_contributions",
  "party_contributions",
  "candidate_contributions",
  "candidate_loans",
  "other_loans",
  "transfers_from_authorized",
]);

const DESIGNATIONS: Record<string, string> = {
  A: "Authorized by a candidate",
  B: "Lobbyist / registrant PAC",
  D: "Leadership PAC",
  J: "Joint fundraiser",
  P: "Principal campaign committee",
  U: "Unauthorized",
};

const linkClass = "font-semibold text-govblue-600 underline-offset-2 hover:underline";

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parseInteger(value: string | undefined, min: number, max: number): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
}

function pageHref(candidate: CampaignMoneyCandidate, offset: number, returnTo: string, search: string, sort: string): string {
  const query = new URLSearchParams({ cycle: String(candidate.finance_cycle), returnTo });
  if (offset > 0) query.set("offset", String(offset));
  if (search) query.set("q", search);
  query.set("sort", sort);
  return `/money/${encodeURIComponent(candidate.candidate_id)}?${query.toString()}`;
}

function InflowChart({ candidate }: { candidate: CampaignMoneyCandidate }) {
  const fields = AMOUNTS.filter((amount) => INFLOW_FIELDS.has(amount.key))
    .map((amount) => ({ ...amount, value: candidate[amount.key] }));
  const maximum = maxPositiveMoney(fields.map((field) => field.value));
  if (maximum === null) {
    return (
      <DataState kind="empty" title="No positive amounts in the selected fields">
        Zero, negative and unreported values remain visible in the financial details below.
      </DataState>
    );
  }
  const positive = fields.filter((field) => {
    const cents = moneyCents(field.value);
    return cents !== null && cents > BigInt(0);
  });
  return (
    <ChartFigure
      title="Selected reported inflow fields (USD)"
      period={`${candidate.finance_cycle} FEC finance cycle · latest report through ${
        candidate.coverage_end ? formatDate(candidate.coverage_end) : "not reported"
      }`}
      summary="Bars are relative to the largest positive field shown. These fields can overlap and are not slices of a total; do not add them together."
      legend={[{ label: "FEC-reported amount (USD)", swatch: "bg-emerald-600" }]}
      source="Federal Election Commission, all-candidates financial summary"
      coverage="Only positive values are charted. Zero, negative and unreported fields remain in the financial details below; transfers can double-count activity."
      table={{
        head: ["Reported field", "Amount (USD)"],
        rows: positive.map((field) => [field.label, formatMoneyExact(field.value)]),
      }}
    >
      <div aria-hidden="true" className="space-y-3">
        {positive.map((field) => (
          <div key={field.key}>
            <div className="flex flex-wrap justify-between gap-x-4 text-sm">
              <span className="font-medium text-ink">{field.label}</span>
              <span className="tabular-nums text-ink-soft">{formatMoneyExact(field.value)}</span>
            </div>
            <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-sunken">
              <div
                className="h-full rounded-full bg-emerald-600"
                style={{ width: `${moneyPercent(field.value, maximum)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </ChartFigure>
  );
}

async function loadDetail(
  candidateId: string,
  cycle: number | undefined,
  offset: number,
  search: string,
  sort: string,
): Promise<{ data: CampaignMoneyDetail; nowMs: number } | "missing" | null> {
  try {
    const query = new URLSearchParams();
    if (cycle !== undefined) query.set("cycle", String(cycle));
    if (offset > 0) query.set("offset", String(offset));
    if (search) query.set("q", search);
    query.set("sort", sort);
    const data = await apiGet<CampaignMoneyDetail>(
      `/api/money/candidates/${encodeURIComponent(candidateId)}?${query.toString()}`,
    );
    if (!Number.isSafeInteger(data.filtered_linkage_count)
      || data.filtered_linkage_count < 0 || data.filtered_linkage_count > data.linkage_count) {
      throw new Error("Candidate finance returned an invalid filtered linkage count");
    }
    const nowMs = parseFreshnessReferenceTime(data.generated_at);
    for (const key of ["receipts", "disbursements", "cash_on_hand", "debts"] as const) {
      moneyCents(data.candidate[key]);
    }
    for (const amount of AMOUNTS) moneyCents(data.candidate[amount.key]);
    return { data, nowMs };
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return "missing";
    console.error("Candidate campaign finance could not be loaded", error);
    return null;
  }
}

export default async function CandidateMoneyPage({
  params,
  searchParams,
}: {
  params: Promise<{ candidateId: string }>;
  searchParams: SearchParams;
}) {
  const { candidateId } = await params;
  const query = await searchParams;
  const rawCycle = first(query.cycle);
  const rawOffset = first(query.offset);
  const browse = readListQuery(query, ["recent", "committee", "designation"], "recent");
  const cycle = rawCycle ? parseInteger(rawCycle, 2000, 2098) : undefined;
  const offset = rawOffset ? parseInteger(rawOffset, 0, 1_000_000) : 0;
  const invalid = !/^[HSP][A-Z0-9]{8}$/.test(candidateId)
    || (Boolean(rawCycle) && (cycle === undefined || cycle % 2 !== 0))
    || offset === undefined || browse.invalid;
  const returnTo = safeMoneyReturn(first(query.returnTo));
  const response = invalid ? null : await loadDetail(candidateId, cycle, offset ?? 0, browse.q, browse.sort);
  const data = response && response !== "missing" ? response.data : null;
  const candidate = data?.candidate ?? null;
  const freshness = data && response && response !== "missing"
    ? classifyFreshness("fec_candidate_totals", data.coverage.fetched_at, response.nowMs)
    : "never";
  const futureDate = candidate?.coverage_end && data
    ? candidate.coverage_end > data.coverage.fetched_at.slice(0, 10)
    : false;

  return (
    <>
      <main className="min-h-screen bg-canvas pb-20">
        <PageBanner eyebrow="FEC candidate financial summary" title={candidate?.name ?? "Candidate finance"}>
          {candidate ? (
            <>{candidate.candidate_id} · {candidate.finance_cycle} finance cycle</>
          ) : (
            "Candidate-level public filings and committee linkages."
          )}
        </PageBanner>
        <div className="mx-auto max-w-6xl space-y-7 px-6 pt-8">
          <Link className={`inline-block text-sm ${linkClass}`} href={moneyReturnHref(returnTo, candidateId)}>
            ← Back to {returnTo.startsWith("/elections") ? "elections" : "campaign money"}
          </Link>
          {invalid ? (
            <DataState kind="error" title="Invalid candidate or filters">
              Candidate IDs, finance cycles and page offsets must be valid.
            </DataState>
          ) : response === "missing" ? (
            <DataState kind="missing" title="This candidate financial record is not available">
              The candidate may not appear in the FEC financial-summary file, or that cycle may not
              be loaded. This does not establish zero activity.
            </DataState>
          ) : !data || !candidate ? (
            <DataState kind="error" title="Candidate campaign finance could not load">
              Please try again or check <Link className={linkClass} href="/status">data pipeline status</Link>.
            </DataState>
          ) : (
            <>
              <DataState kind="partial" title="How to read these numbers">
                These are FEC candidate-level gross figures, not a count of unique contributions.
                Authorized committees may transfer money between one another, causing some activity
                to appear more than once. Cash can include funds from earlier cycles.
              </DataState>
              {futureDate && (
                <DataState kind="partial" title="The FEC-reported coverage date is in the future">
                  The publisher&rsquo;s date is preserved; it should not be read as a completed reporting period.
                </DataState>
              )}
              {freshness === "stale" && (
                <DataState kind="stale">This candidate-finance snapshot may be overdue for refresh.</DataState>
              )}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Gross receipts" value={formatMoneyExact(candidate.receipts)} detail="May include transfers and loans" />
                <Metric label="Disbursements" value={formatMoneyExact(candidate.disbursements)} detail="FEC-reported gross total" />
                <Metric label="Cash on hand" value={formatMoneyExact(candidate.cash_on_hand)} detail="End of the most recent report" />
                <Metric label="Debts owed" value={formatMoneyExact(candidate.debts)} detail="Reported by authorized committees" />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-soft">
                <p>
                  Latest report through: {candidate.coverage_end ? formatDate(candidate.coverage_end) : "not reported"}
                  {" · "}FEC summary file modified:{" "}
                  {data.coverage.summary_last_modified
                    ? formatMeetingTime(data.coverage.summary_last_modified)
                    : "not reported"}
                </p>
                <FreshnessBadge state={freshness} />
              </div>

              <Panel level={2} title="Reported inflow comparison" eyebrow="Separate source fields">
                <InflowChart candidate={candidate} />
              </Panel>

              <Panel level={2} title="Reported financial details" eyebrow="Separate source fields">
                <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
                  {AMOUNTS.map((amount) => (
                    <div key={amount.key}>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                        {amount.label}
                      </dt>
                      <dd className="mt-1 font-semibold tabular-nums text-ink">
                        {formatMoneyExact(candidate[amount.key])}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-5 text-sm leading-6 text-ink-soft">
                  These categories can overlap and are not intended to be added together. The FEC
                  summary does not give a complete breakdown of every receipt or disbursement.
                </p>
              </Panel>

              <Panel level={2} title="Candidate and reporting context" eyebrow="FEC source identities">
                <p className="mb-4 text-sm text-ink-soft">
                  <CandidateMemberLink match={candidate.member_match} />
                </p>
                <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div><dt className="text-ink-muted">Office</dt><dd className="font-semibold text-ink">{{ H: "House", S: "Senate", P: "President" }[candidate.office]}</dd></div>
                  <div><dt className="text-ink-muted">State / district</dt><dd className="font-semibold text-ink">{[candidate.state, candidate.office === "H" ? candidate.district : null].filter(Boolean).join(" / ") || "Not reported"}</dd></div>
                  <div><dt className="text-ink-muted">Party code</dt><dd className="font-semibold text-ink">{candidate.party ?? "Not reported"}</dd></div>
                  <div><dt className="text-ink-muted">Candidate ID</dt><dd className="font-mono font-semibold text-ink">{candidate.candidate_id}</dd></div>
                </dl>
                {data.catalog_match ? (
                  <p className="mt-4 text-sm leading-6 text-ink-soft">
                    The separately refreshed OpenFEC candidate catalog has the same FEC ID for this
                    finance cycle. Its reported election years:{" "}
                    {data.catalog_match.election_years.length
                      ? data.catalog_match.election_years.join(", ")
                      : "not reported"}
                    . A reporting cycle is not proof of ballot access or an election result.
                  </p>
                ) : (
                  <p className="mt-4 text-sm leading-6 text-ink-soft">
                    No matching FEC ID is currently available in the separately refreshed candidate
                    catalog. The independently resolved member-profile link above uses the
                    Bioguide crosswalk, not this catalog or a name match.
                  </p>
                )}
              </Panel>

              <Panel level={2} title="FEC-reported committee links" eyebrow={`${data.linkage_count.toLocaleString()} source records`}>
                <ListToolbar
                  label="Search committee links"
                  searchPlaceholder="Committee ID, designation or type code"
                  searchValue={browse.q}
                  sortValue={browse.sort}
                  resetHref={pageHref(candidate, 0, returnTo, "", "recent")}
                  sorts={[{ value: "recent", label: "Election year" }, { value: "committee", label: "Committee ID" }, { value: "designation", label: "Designation" }]}
                />
                <p className="mb-4 text-sm leading-6 text-ink-soft">
                  These are source-reported relationships for the {candidate.finance_cycle} FEC
                  cycle. Election years and designations are shown as filed; a link does not prove a
                  committee is currently active or that its finances are included in this total.
                </p>
                <p className="mb-4 text-xs leading-5 text-ink-muted">
                  The linkage file was modified{" "}
                  {data.coverage.linkage_last_modified
                    ? formatMeetingTime(data.coverage.linkage_last_modified)
                    : "at an unreported time"}
                  . The FEC publishes the linkage and summary files separately, so their source
                  update times can differ.
                </p>
                {data.linkages.length === 0 ? (
                  <DataState kind="empty" title={browse.q && !data.filtered_linkage_count ? "No committee links match this search" : data.linkage_count ? "No links on this page" : "No links in this FEC file"}>
                    This is not proof that the candidate has no committees.
                  </DataState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <caption className="sr-only">FEC candidate and committee linkage records</caption>
                      <thead className="border-b border-line text-xs uppercase text-ink-muted">
                        <tr>
                          <th scope="col" className="px-3 py-3">Committee ID</th>
                          <th scope="col" className="px-3 py-3">Designation</th>
                          <th scope="col" className="px-3 py-3">Candidate election year</th>
                          <th scope="col" className="px-3 py-3">FEC cycle</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {data.linkages.map((link) => (
                          <tr key={link.linkage_id}>
                            <th scope="row" className="px-3 py-3 font-medium">
                              {link.committee_id ? (
                                <a
                                  className={linkClass}
                                  href={`https://www.fec.gov/data/committee/${encodeURIComponent(link.committee_id)}/`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {link.committee_id}
                                </a>
                              ) : "Not reported"}
                            </th>
                            <td className="px-3 py-3 text-ink-soft">
                              {link.designation
                                ? DESIGNATIONS[link.designation] ?? `FEC designation ${link.designation}`
                                : "Not reported"}
                            </td>
                            <td className="px-3 py-3 text-ink-soft">
                              {link.candidate_election_year}
                              {link.candidate_election_year_outside_supported_range && (
                                <span className="block text-xs text-ink-muted">
                                  Outside 1900–2100; unverified source value.
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-3 text-ink-soft">{link.fec_election_year}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <nav aria-label="Committee link pages" className="mt-4 flex flex-wrap gap-5 text-sm">
                  {data.offset > 0 && (
                    <ListPageLink className={linkClass} href={pageHref(candidate, Math.max(0, data.offset - data.limit), returnTo, browse.q, browse.sort)}>
                      Previous
                    </ListPageLink>
                  )}
                  {data.offset + data.linkages.length < data.filtered_linkage_count && data.linkages.length > 0 && (
                    <ListPageLink className={linkClass} href={pageHref(candidate, data.offset + data.limit, returnTo, browse.q, browse.sort)}>
                      Next
                    </ListPageLink>
                  )}
                  <span role="status" className="text-ink-muted">
                    {data.linkages.length ? (data.offset + 1).toLocaleString() : "0"}–{data.linkages.length ? (data.offset + data.linkages.length).toLocaleString() : "0"} of {data.filtered_linkage_count.toLocaleString()} matching link records ({data.linkage_count.toLocaleString()} total)
                  </span>
                </nav>
              </Panel>

              <p className="text-sm leading-6 text-ink-soft">
                <a className={linkClass} href={`https://www.fec.gov/data/candidate/${encodeURIComponent(candidate.candidate_id)}/`} target="_blank" rel="noreferrer">
                  Open this candidate at the FEC
                </a>
                {" · "}
                <a className={linkClass} href="https://www.fec.gov/campaign-finance-data/candidate-committee-linkage-file-description/" target="_blank" rel="noreferrer">
                  FEC linkage file description
                </a>
                {" · "}
                <Link className={linkClass} href={`/elections?cycle=${candidate.finance_cycle}`}>Browse the candidate catalog</Link>
              </p>
            </>
          )}
        </div>
      </main>
    </>
  );
}
