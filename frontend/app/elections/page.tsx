import Link from "next/link";

import { formatDate } from "@/components/DetailKit";
import { apiGet } from "@/lib/api";
import { hasNormalizedCalendarRange } from "@/lib/election-calendar.mjs";
import { classifyFreshness, parseFreshnessReferenceTime } from "@/lib/freshness.mjs";
import {
  moneyCandidateAnchor,
  moneyCandidateHref,
  supportsMoneyDetail,
} from "@/lib/money-navigation.mjs";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Elections",
  description:
    "Browse FEC-reported federal election dates and candidate registrations. Ballot access and election results are not yet integrated.",
};

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

type Candidate = {
  candidate_id: string;
  finance_cycle: number;
  name: string | null;
  office: "H" | "S" | "P" | null;
  office_full: string | null;
  state: string | null;
  district: string | null;
  party: string | null;
  party_full: string | null;
  candidate_status: string | null;
  incumbent_challenge: string | null;
  first_file_date: string | null;
  last_file_date: string | null;
  cycles: number[];
  election_years: number[];
  principal_committees: Record<string, unknown>[];
};

type CandidateGrouping = {
  office: "H" | "S" | "P" | null;
  office_full: string | null;
  state: string | null;
  district: string | null;
  candidate_count: number;
};

type ElectionCandidates = {
  generated_at: string;
  finance_cycle: number;
  available: boolean;
  complete: boolean;
  candidate_count: number;
  expected_count: number | null;
  fetched_at: string | null;
  filtered_count: number;
  limit: number;
  offset: number;
  groupings: CandidateGrouping[];
  candidates: Candidate[];
};

type CalendarEvent = {
  calendar_year: number;
  event_id: number;
  category: string;
  summary: string;
  description: string | null;
  location: string | null;
  state: string[];
  start_date: string;
  end_date: string | null;
  end_date_normalized?: boolean;
  url: string | null;
};

type ElectionCalendar = {
  generated_at: string;
  calendar_year: number;
  available: boolean;
  complete: boolean;
  event_count: number;
  expected_count: number | null;
  fetched_at: string | null;
  events: CalendarEvent[];
};

type Filters = {
  cycle?: number;
  electionYear?: number;
  office?: "H" | "S" | "P";
  state?: string;
  district?: string;
  party?: string;
  q?: string;
  offset?: number;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function boundedInt(value: string | undefined, min: number, max: number): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
}

function readFilters(params: Record<string, string | string[] | undefined>): {
  filters: Filters;
  invalid: boolean;
} {
  const raw = {
    cycle: first(params.cycle),
    electionYear: first(params.election_year),
    office: first(params.office),
    state: first(params.state),
    district: first(params.district),
    party: first(params.party),
    q: first(params.q),
    offset: first(params.offset),
  };
  const filters: Filters = {};
  let invalid = false;

  if (raw.cycle !== undefined && raw.cycle !== "") {
    const value = boundedInt(raw.cycle, 1979, 2100);
    if (value === undefined) invalid = true;
    else filters.cycle = value;
  }
  if (raw.electionYear !== undefined && raw.electionYear !== "") {
    const value = boundedInt(raw.electionYear, 1979, 2100);
    if (value === undefined) invalid = true;
    else filters.electionYear = value;
  }
  if (raw.office !== undefined && raw.office !== "") {
    if (raw.office === "H" || raw.office === "S" || raw.office === "P") {
      filters.office = raw.office;
    } else invalid = true;
  }
  if (raw.state !== undefined && raw.state.trim() !== "") {
    if (/^[A-Za-z]{2}$/.test(raw.state)) filters.state = raw.state.toUpperCase();
    else invalid = true;
  }
  if (raw.district !== undefined && raw.district.trim() !== "") {
    if (/^[0-9]{2}$/.test(raw.district)) filters.district = raw.district;
    else invalid = true;
  }
  if (raw.party !== undefined && raw.party.trim() !== "") {
    if (/^[A-Za-z]{1,3}$/.test(raw.party)) filters.party = raw.party.toUpperCase();
    else invalid = true;
  }
  if (raw.q !== undefined && raw.q.trim() !== "") {
    if (raw.q.trim().length > 0 && raw.q.length <= 100) filters.q = raw.q.trim();
    else invalid = true;
  }
  if (raw.offset !== undefined && raw.offset !== "") {
    const value = boundedInt(raw.offset, 0, 1_000_000);
    if (value === undefined) invalid = true;
    else filters.offset = value;
  }

  return { filters, invalid };
}

function apiPath(filters: Filters): string {
  const query = new URLSearchParams();
  if (filters.cycle !== undefined) query.set("cycle", String(filters.cycle));
  if (filters.electionYear !== undefined) {
    query.set("election_year", String(filters.electionYear));
  }
  if (filters.office) query.set("office", filters.office);
  if (filters.state) query.set("state", filters.state);
  if (filters.district) query.set("district", filters.district);
  if (filters.party) query.set("party", filters.party);
  if (filters.q) query.set("q", filters.q);
  if (filters.offset) query.set("offset", String(filters.offset));
  query.set("limit", "50");
  return `/api/elections/candidates?${query.toString()}`;
}

function hrefFor(offset: number, cycle: number, filters: Filters): string {
  const next = new URLSearchParams();
  next.set("cycle", String(cycle));
  if (filters.electionYear !== undefined) {
    next.set("election_year", String(filters.electionYear));
  }
  if (filters.office) next.set("office", filters.office);
  if (filters.state) next.set("state", filters.state);
  if (filters.district) next.set("district", filters.district);
  if (filters.party) next.set("party", filters.party);
  if (filters.q) next.set("q", filters.q);
  if (offset > 0) next.set("offset", String(offset));
  return `/elections?${next.toString()}`;
}

function groupingName(grouping: CandidateGrouping): string {
  const office = grouping.office_full ?? grouping.office ?? "Federal office";
  const location = grouping.state ?? (grouping.office === "P" ? "National" : "Location not reported");
  const district = grouping.office === "H" && grouping.district
    ? `District ${grouping.district}`
    : null;
  return [office, location, district].filter(Boolean).join(" · ");
}

function candidateStatus(code: string | null): string {
  const labels: Record<string, string> = {
    C: "Present candidate",
    F: "Future candidate",
    N: "Not yet a candidate",
    P: "Prior candidate",
  };
  return code ? labels[code] ?? `FEC status ${code}` : "FEC status not reported";
}

function withReferenceTime<T extends { generated_at: string }>(data: T): {
  data: T;
  nowMs: number;
} {
  return { data, nowMs: parseFreshnessReferenceTime(data.generated_at) };
}

async function loadCandidates(filters: Filters): Promise<{
  data: ElectionCandidates;
  nowMs: number;
} | null> {
  try {
    return withReferenceTime(await apiGet<ElectionCandidates>(apiPath(filters)));
  } catch (error) {
    console.error(error);
    return null;
  }
}

async function loadCalendar(year: number): Promise<{
  data: ElectionCalendar;
  nowMs: number;
} | null> {
  try {
    return withReferenceTime(
      await apiGet<ElectionCalendar>(
        `/api/elections/calendar?year=${encodeURIComponent(String(year))}`,
      ),
    );
  } catch (error) {
    console.error(error);
    return null;
  }
}

export default async function ElectionsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const { filters, invalid } = readFilters(params);
  const candidateResponse = await loadCandidates(filters);
  const data = candidateResponse?.data ?? null;
  const cycle = data?.finance_cycle ?? filters.cycle ?? 2026;
  const calendarResponse = await loadCalendar(cycle);
  const calendar = calendarResponse?.data ?? null;
  const calendarIsStale = calendarResponse
    ? classifyFreshness(
        "fec_election_calendar",
        calendarResponse.data.fetched_at,
        calendarResponse.nowMs,
      ) === "stale"
    : false;
  const isStale = candidateResponse
    ? classifyFreshness(
        "fec_candidates",
        candidateResponse.data.fetched_at,
        candidateResponse.nowMs,
      ) === "stale"
    : false;
  const previousOffset = Math.max(0, (filters.offset ?? 0) - 50);
  const nextOffset = (filters.offset ?? 0) + 50;

  return (
    <main className="min-h-screen bg-slate-warm-50 pb-20 pt-28">
      <div className="mx-auto max-w-7xl px-6">
        <header className="rounded-3xl bg-govnavy px-6 py-8 text-white shadow-xl sm:px-10 sm:py-10">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-200">
            Federal election workspace
          </p>
          <h1 className="mt-3 font-display text-4xl font-bold tracking-tight sm:text-5xl">
            Candidate registry
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-200 sm:text-lg">
            Explore Federal Election Commission candidate registrations by office, state, and
            reported election year. FEC registration does not establish ballot access, a win, or
            members-elect status.
          </p>
          <div className="mt-6 flex flex-wrap gap-3 text-sm">
            <a
              href="https://www.fec.gov/data/candidates/"
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-white/30 px-4 py-2 font-semibold transition hover:bg-white/10"
            >
              Open FEC candidate records
            </a>
            <a
              href="https://www.fec.gov/introduction-campaign-finance/election-and-voting-information/"
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-white/30 px-4 py-2 font-semibold transition hover:bg-white/10"
            >
              FEC election information
            </a>
          </div>
        </header>

        <section className="mt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-govblue-700">
                OpenFEC · Election Dates
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-govnavy">
                FEC calendar events · {calendar?.calendar_year ?? cycle}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-warm-600">
                The FEC category includes primaries, general and special elections, runoffs, and
                party conventions. These entries are not ballot-access certification, election
                results, or a complete state and local calendar.
              </p>
            </div>
            <p className="text-sm text-slate-warm-500">
              {calendar?.fetched_at ? (
                <>
                  {calendar.event_count.toLocaleString()} events ·{" "}
                  Updated {formatDate(calendar.fetched_at)}
                  {calendarIsStale && <span className="ml-1 font-semibold">· Refresh may be overdue</span>}
                </>
              ) : (
                "No refresh recorded"
              )}
            </p>
          </div>

          {!calendar ? (
            <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-950">
              FEC election dates could not be loaded. Please try again later or check source freshness.
            </p>
          ) : !calendar.available || !calendar.complete ? (
            <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950">
              No complete FEC election-date snapshot is available for {calendar.calendar_year}.
              This is unavailable data, not a zero-event result.
            </p>
          ) : calendar.events.length === 0 ? (
            <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950">
              No stored events are available despite the calendar coverage record. Please check
              source freshness or try another refresh.
            </p>
          ) : (
            <>
              {calendar.events.some((event) => !hasNormalizedCalendarRange(event)) && (
                <p role="status" className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
                  Event end dates may be unavailable until the updated calendar pipeline completes
                  a successful refresh and confirms how their date ranges should be interpreted.
                </p>
              )}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {calendar.events.map((event) => (
                  <article
                    key={`${event.calendar_year}-${event.event_id}`}
                    className="rounded-2xl border border-slate-warm-200 bg-white p-5 shadow-sm"
                  >
                    <p className="text-sm font-semibold text-govblue-700">
                      <time dateTime={event.start_date}>{formatDate(event.start_date)}</time>
                      {hasNormalizedCalendarRange(event) && event.end_date && event.end_date !== event.start_date && (
                        <> – <time dateTime={event.end_date}>{formatDate(event.end_date)}</time></>
                      )}
                    </p>
                    <h3 className="mt-2 font-semibold text-govnavy">{event.summary}</h3>
                    {event.location && <p className="mt-1 text-sm text-slate-warm-600">{event.location}</p>}
                    {event.description && (
                      <p className="mt-3 text-sm leading-6 text-slate-warm-700">{event.description}</p>
                    )}
                    {event.url?.startsWith("https://www.fec.gov/") && (
                      <a
                        href={event.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 inline-block text-sm font-semibold text-govblue-700 hover:underline"
                      >
                        FEC event details
                      </a>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="mt-8 rounded-2xl border border-slate-warm-200 bg-white p-5 shadow-sm">
          <form action="/elections" method="get" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-sm font-semibold text-slate-warm-700">
              FEC finance cycle
              <input
                type="number"
                name="cycle"
                min={1979}
                max={2100}
                defaultValue={filters.cycle ?? cycle}
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal"
              />
            </label>
            <label className="text-sm font-semibold text-slate-warm-700">
              Election year
              <input
                type="number"
                name="election_year"
                min={1979}
                max={2100}
                defaultValue={filters.electionYear}
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal"
              />
            </label>
            <label className="text-sm font-semibold text-slate-warm-700">
              Federal office
              <select
                name="office"
                defaultValue={filters.office ?? ""}
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 bg-white px-3 py-2 font-normal"
              >
                <option value="">All offices</option>
                <option value="H">House</option>
                <option value="S">Senate</option>
                <option value="P">President</option>
              </select>
            </label>
            <label className="text-sm font-semibold text-slate-warm-700">
              State or territory
              <input
                type="text"
                name="state"
                maxLength={2}
                defaultValue={filters.state}
                placeholder="e.g. CA"
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal uppercase"
              />
            </label>
            <label className="text-sm font-semibold text-slate-warm-700">
              House district
              <input
                type="text"
                name="district"
                maxLength={2}
                defaultValue={filters.district}
                placeholder="e.g. 01"
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal"
              />
            </label>
            <label className="text-sm font-semibold text-slate-warm-700">
              Party code
              <input
                type="text"
                name="party"
                maxLength={3}
                defaultValue={filters.party}
                placeholder="e.g. DEM"
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal uppercase"
              />
            </label>
            <label className="text-sm font-semibold text-slate-warm-700 sm:col-span-2">
              Candidate name
              <input
                type="search"
                name="q"
                maxLength={100}
                defaultValue={filters.q}
                className="mt-1.5 w-full rounded-lg border border-slate-warm-300 px-3 py-2 font-normal"
              />
            </label>
            <div className="flex items-end gap-3">
              <button
                type="submit"
                className="rounded-lg bg-govblue-600 px-5 py-2.5 font-semibold text-white transition hover:bg-govblue-700"
              >
                Apply filters
              </button>
              <Link href="/elections" className="py-2.5 text-sm font-semibold text-govblue-700 hover:underline">
                Clear
              </Link>
            </div>
          </form>
        </section>

        {invalid && (
          <p role="status" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
            One or more invalid URL filters were ignored. Use two-letter state codes, two-digit
            districts, and a valid office selection.
          </p>
        )}

        {!data ? (
          <section role="alert" className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-950">
            <h2 className="font-semibold">Election data could not be loaded</h2>
            <p className="mt-2 text-sm">Please try again later or check the data pipeline status.</p>
            <Link href="/status" className="mt-3 inline-block font-semibold underline">
              View data pipeline status
            </Link>
          </section>
        ) : !data.available || !data.complete ? (
          <section role="status" className="mt-8 rounded-2xl border border-amber-300 bg-amber-50 p-6 text-amber-950">
            <h2 className="font-semibold">No complete candidate catalog is available for cycle {cycle}</h2>
            <p className="mt-2 text-sm">
              This is unavailable data, not a zero-candidate result. The catalog is only published
              after the full OpenFEC page walk succeeds.
            </p>
            <Link href="/status" className="mt-3 inline-block font-semibold underline">
              Check source freshness
            </Link>
          </section>
        ) : (
          <>
            <section className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 px-5 py-4 text-sm text-blue-950">
              <p>
                <strong>{data.candidate_count.toLocaleString()}</strong> candidate records collected
                in the latest completed FEC page walk;{" "}
                <strong>{data.filtered_count.toLocaleString()}</strong> match these filters.
                {data.expected_count !== null && (
                  <> OpenFEC reported {data.expected_count.toLocaleString()} records; its count may be approximate.</>
                )}
                {" "}The source can change while pages are collected.
              </p>
              <p className="text-blue-800">
                Snapshot: {data.fetched_at ? formatDate(data.fetched_at) : "unknown"}
                {isStale && <span className="ml-2 font-semibold">· Refresh may be overdue</span>}
              </p>
            </section>

            <section className="mt-8">
              <div className="mb-4">
                <h2 className="font-display text-2xl font-bold text-govnavy">FEC-reported office groupings</h2>
                <p className="mt-1 text-sm text-slate-warm-600">
                  Grouped by office, state, and district as reported by the FEC. This is not a
                  certified contest or seat list; special elections and state primary dates are not
                  distinguished here.
                </p>
              </div>
              {data.groupings.length === 0 ? (
                <p className="rounded-xl border border-slate-warm-200 bg-white p-5 text-slate-warm-600">
                  No office groupings match these filters.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-2xl border border-slate-warm-200 bg-white shadow-sm">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-warm-100 text-xs uppercase tracking-wide text-slate-warm-600">
                      <tr>
                        <th className="px-4 py-3">FEC race grouping</th>
                        <th className="px-4 py-3 text-right">Registered candidates</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-warm-100">
                      {data.groupings.map((grouping) => (
                        <tr
                          key={`${grouping.office ?? "?"}-${grouping.state ?? "US"}-${grouping.district ?? "00"}`}
                        >
                          <td className="px-4 py-3 font-medium text-govnavy">{groupingName(grouping)}</td>
                          <td className="px-4 py-3 text-right tabular-nums text-slate-warm-700">
                            {grouping.candidate_count.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="mt-10">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="font-display text-2xl font-bold text-govnavy">Candidate records</h2>
                  <p className="mt-1 text-sm text-slate-warm-600">
                    FEC candidate IDs remain separate from GovMap member identities.
                  </p>
                </div>
                <p className="text-sm text-slate-warm-500">
                  Showing {data.candidates.length.toLocaleString()} of {data.filtered_count.toLocaleString()}
                </p>
              </div>

              {data.filtered_count === 0 ? (
                <p className="rounded-xl border border-slate-warm-200 bg-white p-5 text-slate-warm-600">
                  No candidate records match these filters.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-2xl border border-slate-warm-200 bg-white shadow-sm">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-warm-100 text-xs uppercase tracking-wide text-slate-warm-600">
                      <tr>
                        <th className="px-4 py-3">Candidate</th>
                        <th className="px-4 py-3">Office & location</th>
                        <th className="px-4 py-3">Party</th>
                        <th className="px-4 py-3">FEC status</th>
                        <th className="px-4 py-3">Reported election years</th>
                        <th className="px-4 py-3">Latest filing</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-warm-100">
                      {data.candidates.map((candidate) => (
                        <tr key={`${candidate.finance_cycle}-${candidate.candidate_id}`}>
                          <td className="px-4 py-4">
                            <a
                              href={`https://www.fec.gov/data/candidate/${encodeURIComponent(candidate.candidate_id)}/`}
                              target="_blank"
                              rel="noreferrer"
                              className="font-semibold text-govblue-700 hover:underline"
                            >
                              {candidate.name ?? "Name not reported"}
                            </a>
                            <div className="mt-1 font-mono text-xs text-slate-warm-500">
                              {candidate.candidate_id}
                            </div>
                            {supportsMoneyDetail(candidate.candidate_id, candidate.finance_cycle) && (
                              <Link
                                id={moneyCandidateAnchor(candidate.candidate_id)}
                                href={moneyCandidateHref(
                                  candidate.candidate_id,
                                  candidate.finance_cycle,
                                  hrefFor(data.offset, cycle, filters),
                                )}
                                className="mt-2 inline-block scroll-mt-24 text-xs font-semibold text-govblue-700 hover:underline"
                              >
                                View campaign financial summary
                              </Link>
                            )}
                          </td>
                          <td className="px-4 py-4 text-slate-warm-700">
                            <div>{candidate.office_full ?? candidate.office ?? "Office not reported"}</div>
                            <div className="mt-1 text-xs text-slate-warm-500">
                              {[candidate.state, candidate.office === "H" && candidate.district ? `District ${candidate.district}` : null]
                                .filter(Boolean)
                                .join(" · ") || "Location not reported"}
                            </div>
                          </td>
                          <td className="px-4 py-4 text-slate-warm-700">
                            {candidate.party_full ?? candidate.party ?? "Not reported"}
                          </td>
                          <td className="px-4 py-4 text-slate-warm-700">
                            {candidateStatus(candidate.candidate_status)}
                          </td>
                          <td className="px-4 py-4 tabular-nums text-slate-warm-700">
                            {candidate.election_years.length
                              ? candidate.election_years.join(", ")
                              : "Not reported"}
                          </td>
                          <td className="px-4 py-4 text-slate-warm-700">
                            {candidate.last_file_date ? formatDate(candidate.last_file_date) : "Not reported"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {data.filtered_count > data.offset + data.limit && (
                <div className="mt-5 flex justify-end">
                  <Link
                    href={hrefFor(nextOffset, cycle, filters)}
                    className="rounded-lg border border-slate-warm-300 bg-white px-4 py-2 font-semibold text-govblue-700 hover:bg-slate-warm-100"
                  >
                    Next candidates
                  </Link>
                </div>
              )}
              {data.offset > 0 && (
                <div className="mt-5 flex justify-start">
                  <Link
                    href={hrefFor(previousOffset, cycle, filters)}
                    className="rounded-lg border border-slate-warm-300 bg-white px-4 py-2 font-semibold text-govblue-700 hover:bg-slate-warm-100"
                  >
                    Previous candidates
                  </Link>
                </div>
              )}
            </section>

            <aside className="mt-8 rounded-2xl border border-slate-warm-200 bg-white p-5 text-sm leading-6 text-slate-warm-600">
              <strong className="text-govnavy">Coverage boundary:</strong> this page is an FEC
              registration catalog and candidate-provided race metadata. It does not verify state
              ballot qualification, publish official election results, identify members-elect, or
              determine who will serve in the next Congress. Candidate financial summaries are
              available separately when loaded; committee filings and donor records are not part of
              this workspace. See the{" "}
              <Link href="/status" className="font-semibold text-govblue-700 hover:underline">
                data pipeline status
              </Link>{" "}
              for refresh history.
            </aside>
          </>
        )}
      </div>
    </main>
  );
}
