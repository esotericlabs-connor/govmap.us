import Link from "next/link";

import { ChartFigure } from "@/components/dashboard/ChartFigure";
import { DataState, FreshnessBadge } from "@/components/dashboard/DataState";
import { MoneyStack } from "@/components/dashboard/MoneyStack";
import { Metric, Panel } from "@/components/dashboard/Panel";
import { formatDate } from "@/components/DetailKit";
import { PageBanner } from "@/components/PageBanner";
import { SiteFooter } from "@/components/SiteFooter";
import { apiGet } from "@/lib/api";
import type { CampaignMoneyCandidate, CampaignMoneyList } from "@/lib/campaign-money";
import { classifyFreshness, parseFreshnessReferenceTime } from "@/lib/freshness.mjs";
import { formatMeetingTime } from "@/lib/format";
import {
  formatMoneyCents,
  formatMoneyExact,
  maxPositiveMoney,
  moneyCents,
  moneyPercent,
  moneyStackBlockCents,
} from "@/lib/money.mjs";
import { moneyCandidateAnchor, moneyCandidateHref } from "@/lib/money-navigation.mjs";

export const dynamic = "force-dynamic";
export const metadata = {
  title: "Campaign money",
  description:
    "Explore FEC candidate financial summaries by office, state, district and reporting date.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;
type Office = "H" | "S" | "P";
type Filters = {
  cycle?: number;
  office: Office;
  state?: string;
  district?: string;
  q?: string;
  through?: string;
  offset: number;
};

const fieldClass = "mt-1.5 w-full rounded-lg border border-line bg-canvas px-3 py-2 font-normal text-ink";
const linkClass = "font-semibold text-govblue-600 underline-offset-2 hover:underline";

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function integer(value: string, min: number, max: number): number | undefined {
  if (!/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
}

function readFilters(params: Record<string, string | string[] | undefined>): {
  filters: Filters;
  invalid: boolean;
} {
  const filters: Filters = { office: "H", offset: 0 };
  let invalid = false;
  const cycle = first(params.cycle);
  const office = first(params.office);
  const state = first(params.state)?.trim();
  const district = first(params.district)?.trim();
  const q = first(params.q)?.trim();
  const through = first(params.through);
  const offset = first(params.offset);
  if (cycle) {
    const parsed = integer(cycle, 2000, 2098);
    if (parsed === undefined || parsed % 2 !== 0) invalid = true;
    else filters.cycle = parsed;
  }
  if (office) {
    if (office === "H" || office === "S" || office === "P") filters.office = office;
    else invalid = true;
  }
  if (state) {
    if (/^[A-Za-z]{2}$/.test(state)) filters.state = state.toUpperCase();
    else invalid = true;
  }
  if (district) {
    if (/^\d{2}$/.test(district)) filters.district = district;
    else invalid = true;
  }
  if (q) {
    if (q.length <= 100) filters.q = q;
    else invalid = true;
  }
  if (through) {
    if (validDate(through)) filters.through = through;
    else invalid = true;
  }
  if (offset) {
    const parsed = integer(offset, 0, 1_000_000);
    if (parsed === undefined) invalid = true;
    else filters.offset = parsed;
  }
  if (filters.district && (!filters.state || filters.office !== "H")) invalid = true;
  return { filters, invalid };
}

function queryFor(filters: Filters, cycle?: number, through?: string | null, offset = 0): URLSearchParams {
  const query = new URLSearchParams();
  const selectedCycle = cycle ?? filters.cycle;
  if (selectedCycle !== undefined) query.set("cycle", String(selectedCycle));
  query.set("office", filters.office);
  if (filters.state) query.set("state", filters.state);
  if (filters.district) query.set("district", filters.district);
  if (filters.q) query.set("q", filters.q);
  const selectedDate = through ?? filters.through;
  if (selectedDate) query.set("through", selectedDate);
  if (offset > 0) query.set("offset", String(offset));
  return query;
}

function moneyHref(filters: Filters, data: CampaignMoneyList, offset: number): string {
  return `/money?${queryFor(filters, data.finance_cycle, data.selected_date, offset).toString()}`;
}

function location(candidate: CampaignMoneyCandidate): string {
  const office = { H: "House", S: "Senate", P: "President" }[candidate.office];
  return [
    office,
    candidate.state,
    candidate.office === "H" && candidate.district ? `District ${candidate.district}` : null,
  ].filter(Boolean).join(" · ");
}

async function loadMoney(filters: Filters): Promise<{
  data: CampaignMoneyList;
  nowMs: number;
} | null> {
  try {
    const data = await apiGet<CampaignMoneyList>(
      `/api/money/candidates?${queryFor(filters, undefined, undefined, filters.offset).toString()}`,
    );
    const nowMs = parseFreshnessReferenceTime(data.generated_at);
    for (const candidate of data.candidates) {
      moneyCents(candidate.receipts);
      moneyCents(candidate.disbursements);
      moneyCents(candidate.cash_on_hand);
      moneyCents(candidate.debts);
    }
    return { data, nowMs };
  } catch (error) {
    console.error("Campaign money data could not be loaded", error);
    return null;
  }
}

function CandidateChart({ candidates, through, financeCycle }: {
  candidates: CampaignMoneyCandidate[];
  through: string;
  financeCycle: number;
}) {
  const rows = candidates
    .filter((candidate) => {
      const cents = moneyCents(candidate.receipts);
      return cents !== null && cents > BigInt(0);
    })
    .slice(0, 8);
  if (rows.length === 0) {
    return (
      <DataState kind="empty" title="No positive receipts on this page">
        The table below still shows zero, negative and unreported amounts as supplied by the FEC.
      </DataState>
    );
  }
  const maximum = maxPositiveMoney(rows.map((candidate) => candidate.receipts));
  const block = moneyStackBlockCents(maximum);
  if (block === null) throw new Error("Cannot determine a positive money-stack scale");
  return (
    <ChartFigure
      title="Reported gross receipts (USD)"
      period={`${financeCycle} two-year FEC finance cycle · latest report through ${formatDate(through)}`}
      summary="Each bar is relative to the highest candidate on this page. Bars and stacks represent individual FEC candidate IDs, not sums of people or committees."
      legend={[{ label: "Gross receipts reported to the FEC (USD)", swatch: "bg-emerald-600" }]}
      source="Federal Election Commission, all-candidates financial summary"
      coverage={`Each illustrated stack level represents up to ${formatMoneyCents(block)}; the final level is rounded up and may be partial. This shared scale applies to the candidates shown on this page and can change on other pages or filters. Exact amounts are in the table. Gross receipts may include transfers, loans and double-counted committee activity.`}
      table={{
        head: ["Candidate / FEC ID", "Gross receipts (USD)"],
        rows: rows.map((candidate) => [
          `${candidate.name ?? "Name not reported"} (${candidate.candidate_id})`,
          formatMoneyExact(candidate.receipts),
        ]),
      }}
    >
      <div aria-hidden="true" className="space-y-3">
        {rows.map((candidate) => (
          <div key={candidate.candidate_id} className="flex items-center gap-3">
            <MoneyStack amount={candidate.receipts} maximum={maximum} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-ink">
                {candidate.name ?? "Name not reported"}
              </p>
              <p className="text-xs text-ink-muted">{candidate.candidate_id} · {location(candidate)}</p>
              <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-sunken">
                <div
                  className="h-full rounded-full bg-emerald-600"
                  style={{ width: `${moneyPercent(candidate.receipts, maximum)}%` }}
                />
              </div>
              <p className="mt-1 text-xs font-semibold tabular-nums text-ink">
                {formatMoneyExact(candidate.receipts)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </ChartFigure>
  );
}

export default async function CampaignMoneyPage({ searchParams }: { searchParams: SearchParams }) {
  const { filters, invalid } = readFilters(await searchParams);
  const response = invalid ? null : await loadMoney(filters);
  const data = response?.data ?? null;
  const coverage = data?.coverage ?? null;
  const selectedOutsideList = filters.through && !data?.reporting_dates.some(
    (period) => period.coverage_end === filters.through,
  );
  const sourceState = response && coverage
    ? classifyFreshness("fec_candidate_totals", coverage.fetched_at, response.nowMs)
    : "never";
  const futureDate = data?.selected_date && coverage
    ? data.selected_date > coverage.fetched_at.slice(0, 10)
    : false;

  return (
    <>
      <main className="min-h-screen bg-canvas pb-20">
        <PageBanner eyebrow="Federal campaign finance" title="Follow the campaign money">
          Compare FEC-reported candidate financial summaries by office, location and filing date.
          These are gross receipts to campaigns, not a ranking of individual donors.
        </PageBanner>

        <div className="mx-auto max-w-7xl space-y-7 px-6 pt-8">
          <DataState kind="partial" title="What this first campaign-money view can and cannot show">
            Candidate totals can include loans and transfers between authorized committees; the FEC
            warns that some activity can be counted more than once. We do not add candidate and
            committee totals together. Donor geography, organization rankings and independent
            expenditures are not yet integrated or reconciled.
          </DataState>

          <Panel level={2} title="Explore candidate summaries" eyebrow="FEC financial filings">
            <form action="/money" method="get" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <label className="text-sm font-semibold text-ink-soft">
                Two-year finance cycle
                <input
                  className={fieldClass}
                  type="number"
                  name="cycle"
                  min={2000}
                  max={2098}
                  step={2}
                  defaultValue={filters.cycle ?? data?.finance_cycle ?? ""}
                  placeholder="Configured cycle"
                />
              </label>
              <label className="text-sm font-semibold text-ink-soft">
                Office
                <select className={fieldClass} name="office" defaultValue={filters.office}>
                  <option value="H">House</option>
                  <option value="S">Senate</option>
                  <option value="P">President</option>
                </select>
              </label>
              <label className="text-sm font-semibold text-ink-soft">
                State or territory
                <input
                  className={fieldClass}
                  name="state"
                  maxLength={2}
                  placeholder="Two-letter code, e.g. CA"
                  defaultValue={filters.state ?? ""}
                />
              </label>
              <label className="text-sm font-semibold text-ink-soft">
                House district
                <input
                  className={fieldClass}
                  name="district"
                  maxLength={2}
                  inputMode="numeric"
                  placeholder="Two digits, e.g. 01 or 00"
                  defaultValue={filters.district ?? ""}
                />
                <span className="mt-1 block text-xs font-normal text-ink-muted">
                  Requires a state and House office.
                </span>
              </label>
              <label className="text-sm font-semibold text-ink-soft">
                Candidate name or FEC ID
                <input
                  className={fieldClass}
                  name="q"
                  maxLength={100}
                  defaultValue={filters.q ?? ""}
                />
              </label>
              <label className="text-sm font-semibold text-ink-soft">
                Most recent report through
                <select className={fieldClass} name="through" defaultValue={filters.through ?? ""}>
                  <option value="">Most common available date</option>
                  {selectedOutsideList && filters.through && (
                    <option value={filters.through}>{formatDate(filters.through)} · requested</option>
                  )}
                  {data?.reporting_dates.map((period) => (
                    <option key={period.coverage_end} value={period.coverage_end}>
                      {formatDate(period.coverage_end)} · {period.candidate_count.toLocaleString()} records
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex flex-wrap items-center gap-4 lg:col-span-3">
                <button
                  type="submit"
                  className="rounded-full bg-govblue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-govblue-700"
                >
                  Apply filters
                </button>
                <Link href="/money" className={`text-sm ${linkClass}`}>Clear filters</Link>
              </div>
            </form>
          </Panel>

          {invalid ? (
            <DataState kind="error" title="These filters are invalid">
              Use an even finance cycle, a two-letter state, a two-digit House district, and a valid
              report date. No results were substituted.
            </DataState>
          ) : !data ? (
            <DataState kind="error" title="Campaign money could not load">
              Please try again or check the <Link className={linkClass} href="/status">data pipeline status</Link>.
            </DataState>
          ) : !data.available || !coverage ? (
            <DataState kind="missing" title={`No candidate finance snapshot is available for ${data.finance_cycle}`}>
              A missing snapshot does not mean there was no campaign activity. Check the{" "}
              <Link className={linkClass} href="/status">data pipeline status</Link>.
            </DataState>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Candidate records in file" value={coverage.candidate_count.toLocaleString()} detail="FEC financial-summary file; not every registered candidate" />
                <Metric label="Matching office and location" value={data.matching_count.toLocaleString()} detail="Before the report-date filter" />
                <Metric label="Same report-through date" value={data.filtered_count.toLocaleString()} detail={data.selected_date ? formatDate(data.selected_date) : "No date reported"} />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-soft">
                <p>
                  FEC summary file modified:{" "}
                  {coverage.summary_last_modified ? formatMeetingTime(coverage.summary_last_modified) : "not reported"}
                  {" · "}GovMap fetched: {formatMeetingTime(coverage.fetched_at)}
                </p>
                <FreshnessBadge state={sourceState} />
              </div>
              {sourceState === "stale" && (
                <DataState kind="stale">The last successful candidate-finance refresh may be overdue.</DataState>
              )}
              {futureDate && (
                <DataState kind="partial" title="The FEC-reported coverage date is in the future">
                  GovMap preserves the publisher&rsquo;s date; it should not be read as a completed reporting period.
                </DataState>
              )}
              <p className="text-sm leading-6 text-ink-soft">
                Only records with the same office, finance cycle and latest reported coverage end date
                are compared. Even then, individual authorized committees may report on different
                schedules. A finance cycle is not necessarily a Senate election year.
                {data.reporting_dates_truncated && " The date selector shows only the 100 most common dates."}
              </p>

              {data.selected_date && data.candidates.length > 0 && (
                <Panel level={2} title="Visual comparison" eyebrow="Relative scale, exact amounts">
                  <CandidateChart
                    candidates={data.candidates}
                    through={data.selected_date}
                    financeCycle={data.finance_cycle}
                  />
                </Panel>
              )}

              <Panel level={2} title="Candidate financial records" eyebrow="FEC candidate IDs">
                {data.filtered_count === 0 ? (
                  <DataState kind="empty" title="No records match this report-through date">
                    Try another office, location or date. Candidates not present in the file are not assumed to have zero activity.
                  </DataState>
                ) : data.candidates.length === 0 ? (
                  <DataState kind="empty" title="There are no records on this page">
                    Return to an earlier page to see the matching records.
                  </DataState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm tabular-nums">
                      <caption className="sr-only">
                        Candidate financial records for the selected FEC finance cycle and reporting date
                      </caption>
                      <thead className="border-b border-line text-xs uppercase text-ink-muted">
                        <tr>
                          <th scope="col" className="px-3 py-3">Candidate</th>
                          <th scope="col" className="px-3 py-3">Office and location</th>
                          <th scope="col" className="px-3 py-3 text-right">Gross receipts</th>
                          <th scope="col" className="px-3 py-3 text-right">Disbursements</th>
                          <th scope="col" className="px-3 py-3 text-right">Cash on hand</th>
                          <th scope="col" className="px-3 py-3 text-right">Debts</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {data.candidates.map((candidate) => (
                          <tr key={candidate.candidate_id}>
                            <th scope="row" className="px-3 py-3 font-medium">
                              <Link
                                id={moneyCandidateAnchor(candidate.candidate_id)}
                                className={`${linkClass} scroll-mt-24`}
                                href={moneyCandidateHref(candidate.candidate_id, candidate.finance_cycle, moneyHref(filters, data, data.offset))}
                              >
                                {candidate.name ?? "Name not reported"}
                              </Link>
                              <span className="mt-1 block font-mono text-xs font-normal text-ink-muted">
                                {candidate.candidate_id} · {candidate.party ?? "Party not reported"}
                              </span>
                            </th>
                            <td className="px-3 py-3 text-ink-soft">{location(candidate)}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-right">{formatMoneyExact(candidate.receipts)}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-right">{formatMoneyExact(candidate.disbursements)}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-right">{formatMoneyExact(candidate.cash_on_hand)}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-right">{formatMoneyExact(candidate.debts)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <nav aria-label="Candidate finance pages" className="mt-5 flex flex-wrap items-center gap-5 text-sm">
                  {data.offset > 0 && (
                    <Link className={linkClass} href={moneyHref(filters, data, Math.max(0, data.offset - data.limit))}>
                      Previous
                    </Link>
                  )}
                  {data.offset + data.candidates.length < data.filtered_count && data.candidates.length > 0 && (
                    <Link className={linkClass} href={moneyHref(filters, data, data.offset + data.limit)}>
                      Next
                    </Link>
                  )}
                  <span className="text-ink-muted">
                    Showing {data.candidates.length.toLocaleString()} of {data.filtered_count.toLocaleString()} matching records
                  </span>
                </nav>
              </Panel>

              <Panel level={2} title="Source and coverage" eyebrow="Transparency">
                <div className="space-y-3 text-sm leading-6 text-ink-soft">
                  <p>
                    The FEC&rsquo;s file includes candidates with reported financial activity, including
                    people who are not current members of Congress. FEC IDs are source identities,
                    not proof of ballot access, a win, or a Bioguide match.
                  </p>
                  <p>
                    Individual contributor identities and donor-location rankings are not part of this
                    view. FEC rules restrict the use of contributor information for solicitation and
                    commercial purposes; expanded donor views require a separate use review.
                  </p>
                  <p>
                    <a className={linkClass} href="https://www.fec.gov/campaign-finance-data/all-candidates-file-description/" target="_blank" rel="noreferrer">
                      FEC file description and double-counting guidance
                    </a>
                    {" · "}
                    <a className={linkClass} href="https://www.fec.gov/updates/sale-or-use-contributor-information/" target="_blank" rel="noreferrer">
                      FEC contributor-information restrictions
                    </a>
                    {" · "}
                    <Link className={linkClass} href="/status">Data status</Link>
                  </p>
                </div>
              </Panel>
            </>
          )}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
