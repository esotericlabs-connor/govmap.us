import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { ChartFigure, type LegendItem } from "@/components/dashboard/ChartFigure";
import { DataState, FreshnessBadge, LoadingBlock } from "@/components/dashboard/DataState";
import { Hemicycle } from "@/components/dashboard/Hemicycle";
import { Metric, Panel, PanelLink } from "@/components/dashboard/Panel";
import { WeeklyBars } from "@/components/dashboard/WeeklyBars";
import { CapitolBackdrop } from "@/components/PageBanner";
import {
  apiGet,
  type Overview,
  type OverviewActivity,
  type OverviewMeeting,
  type SourceFreshness,
} from "@/lib/api";
import { classifyFreshness, formatAge } from "@/lib/freshness.mjs";
import { formatDateUTC, formatMeetingTime } from "@/lib/format";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

export const metadata = {
  description:
    "A sourced, nonpartisan overview of the federal government: who holds each seat in Congress, how often each chamber votes, the bills and laws on file, and what's next on the committee calendar.",
};

const NUMBER = new Intl.NumberFormat("en-US");

const LEVELS = [
  { label: "Federal", href: "/", live: true },
  { label: "State", href: "/about#coverage", live: false },
  { label: "Local", href: "/about#coverage", live: false },
] as const;

const BRANCHES = [
  { id: "legislative", branch: "Legislative", name: "Congress", live: true },
  { id: "executive", branch: "Executive", name: "The White House & agencies", live: false },
  { id: "judicial", branch: "Judicial", name: "The federal courts", live: false },
] as const;

type PlannedSource = { what: string; from: string };

const EXECUTIVE_SOURCES: PlannedSource[] = [
  { what: "Presidential documents", from: "GovInfo, Compilation of Presidential Documents" },
  { what: "Executive orders and agency rules", from: "Federal Register" },
  { what: "Nominations", from: "Congress.gov" },
  { what: "Agency budgets and spending", from: "USAspending.gov" },
];

const JUDICIAL_SOURCES: PlannedSource[] = [
  { what: "Article III judges and their service", from: "Federal Judicial Center" },
  { what: "Supreme Court opinions", from: "Supreme Court of the United States" },
  { what: "Federal court opinions", from: "GovInfo, United States Courts Opinions" },
  { what: "Judicial nominations", from: "Congress.gov" },
];

function ordinal(n: number): string {
  const lastTwo = n % 100;
  const last = n % 10;
  if (lastTwo >= 11 && lastTwo <= 13) return `${n}th`;
  return `${n}${last === 1 ? "st" : last === 2 ? "nd" : last === 3 ? "rd" : "th"}`;
}

/** Total of the weeks that were collected; null when none were. */
function sumCollected(values: (number | null)[]): number | null {
  const known = values.filter((v): v is number => v !== null);
  return known.length === 0 ? null : known.reduce((a, b) => a + b, 0);
}

function countOrMissing(value: number | null): string {
  return value === null ? "Not collected" : NUMBER.format(value);
}

function weekLabel(weeks: string[], i: number): string {
  return `${formatDateUTC(weeks[i])}${i === weeks.length - 1 ? " (so far)" : ""}`;
}

function weekRange(weeks: string[]): string {
  if (weeks.length === 0) return "";
  return `Weeks of ${formatDateUTC(weeks[0])} to ${formatDateUTC(weeks[weeks.length - 1])}`;
}

function sourceNamed(sources: SourceFreshness[], name: string): SourceFreshness | undefined {
  return sources.find((s) => s.name === name);
}

// --- Header ---------------------------------------------------------------

function StatusChip({ live }: { live: boolean }) {
  return live ? (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-green-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-green-200">
      <span className="h-1.5 w-1.5 rounded-full bg-green-400" aria-hidden="true" />
      Live
    </span>
  ) : (
    <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/70">
      Planned
    </span>
  );
}

function OverviewHeader() {
  return (
    <section className="chrome relative isolate overflow-hidden bg-govnavy-800 text-white">
      <CapitolBackdrop position="center" priority />
      <div className="mx-auto max-w-7xl px-4 pb-8 pt-28 sm:px-6 sm:pt-32">
        <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-white/60">
              From City Council to Congress
            </p>
            <h1 className="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Federal overview</h1>
            <p className="mt-2 leading-relaxed text-white/80">
              The federal government at a glance, every figure taken from an official public source. Congress is
              live today; the White House, the agencies and the federal courts are the next branches on the way.
            </p>
          </div>
          <nav aria-label="Level of government">
            <ul className="inline-flex rounded-full border border-white/15 bg-white/10 p-1 backdrop-blur">
              {LEVELS.map((level) => (
                <li key={level.label}>
                  <Link
                    href={level.href}
                    aria-current={level.live ? "page" : undefined}
                    className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
                      level.live ? "bg-white text-govnavy shadow" : "text-white/75 hover:text-white"
                    }`}
                  >
                    {level.label}
                    {!level.live && (
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-white/50">
                        Planned
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <nav aria-label="Branches of government" className="mt-6">
          <ul className="grid gap-3 sm:grid-cols-3">
            {BRANCHES.map((b) => (
              <li key={b.id}>
                <a
                  href={`#${b.id}`}
                  className="flex h-full items-start justify-between gap-3 rounded-xl border border-white/15 bg-white/5 px-4 py-3 backdrop-blur transition-colors hover:border-white/30 hover:bg-white/10"
                >
                  <span className="min-w-0">
                    <span className="block text-[11px] font-semibold uppercase tracking-wider text-white/60">
                      {b.branch}
                    </span>
                    <span className="block font-semibold">{b.name}</span>
                  </span>
                  <StatusChip live={b.live} />
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </section>
  );
}

// --- Legislative ----------------------------------------------------------

/** A chart slot with nothing to draw: its title plus the reason why. */
function ChartPlaceholder({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <h4 className="font-display text-sm font-bold text-ink">{title}</h4>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function VotesChart({ activity, publisher }: { activity: OverviewActivity; publisher?: string }) {
  const { weeks, votes, votes_covered_from: from } = activity;
  const title = "Roll-call votes per week";
  const house = sumCollected(votes.house);
  const senate = sumCollected(votes.senate);

  if (house === null && senate === null) {
    return (
      <ChartPlaceholder title={title}>
        <DataState kind="missing">No roll calls are stored for these weeks yet, so there is nothing to count.</DataState>
      </ChartPlaceholder>
    );
  }

  const gaps = [...votes.house, ...votes.senate].some((v) => v === null);
  const legend: LegendItem[] = [
    { label: "House", swatch: "bg-series-house" },
    { label: "Senate", swatch: "bg-series-senate" },
    ...(gaps ? [{ label: "Not collected", dashed: true }] : []),
  ];
  const held = [
    house === null ? null : `${NUMBER.format(house)} in the House`,
    senate === null ? null : `${NUMBER.format(senate)} in the Senate`,
  ].filter((part): part is string => part !== null);
  const startsFrom = (chamber: string, iso: string | null) =>
    `${chamber} ${iso ? `from ${formatDateUTC(iso)}` : "not collected"}`;

  return (
    <ChartFigure
      title={title}
      period={`${weekRange(weeks)} · roll calls held`}
      summary={`${held.join(" and ")} over the last ${weeks.length} weeks, counting the current week so far.`}
      legend={legend}
      source={publisher ?? "Official House and Senate roll-call records"}
      coverage={`Stored roll calls run ${startsFrom("House", from.house)}; ${startsFrom("Senate", from.senate)}.${
        gaps ? " Weeks before a chamber’s first stored roll call show as not collected, not as zero." : ""
      }`}
      table={{
        head: ["Week of", "House", "Senate"],
        rows: weeks.map((_, i) => [
          weekLabel(weeks, i),
          countOrMissing(votes.house[i] ?? null),
          countOrMissing(votes.senate[i] ?? null),
        ]),
      }}
    >
      <WeeklyBars
        weeks={weeks}
        series={[
          { label: "House", values: votes.house, barClass: "bg-series-house" },
          { label: "Senate", values: votes.senate, barClass: "bg-series-senate" },
        ]}
      />
    </ChartFigure>
  );
}

function BillsChart({
  activity,
  congress,
  publisher,
}: {
  activity: OverviewActivity;
  congress: number;
  publisher?: string;
}) {
  const { weeks, bills_introduced: bills } = activity;
  const title = "Measures introduced per week";
  const total = bills.reduce((a, b) => a + b, 0);
  const caveat =
    "GovMap holds the measures sponsored by current members plus recently updated ones, so this is not the official count.";

  if (total === 0) {
    return (
      <ChartPlaceholder title={title}>
        <DataState kind="empty">
          None of the measures on file were introduced in these weeks. {caveat}
        </DataState>
      </ChartPlaceholder>
    );
  }

  return (
    <ChartFigure
      title={title}
      period={`${weekRange(weeks)} · bills and resolutions`}
      summary={`${NUMBER.format(total)} measures on file were introduced over the last ${weeks.length} weeks, counting the current week so far. ${caveat}`}
      legend={[{ label: "Measures introduced", swatch: "bg-series-bills" }]}
      source={publisher ?? "Congress.gov"}
      coverage={`${ordinal(congress)} Congress measures GovMap holds, by introduced date.`}
      table={{
        head: ["Week of", "Introduced"],
        rows: weeks.map((_, i) => [weekLabel(weeks, i), NUMBER.format(bills[i] ?? 0)]),
      }}
    >
      <WeeklyBars weeks={weeks} series={[{ label: "Introduced", values: bills, barClass: "bg-series-bills" }]} />
    </ChartFigure>
  );
}

function statusTone(status: string): string {
  return /cancel/i.test(status)
    ? "border-red-200 bg-red-50 text-red-800"
    : "border-amber-200 bg-amber-50 text-amber-900";
}

function MeetingsPanel({ meetings, source }: { meetings: OverviewMeeting[]; source?: SourceFreshness }) {
  return (
    <Panel eyebrow="On the calendar" title="Upcoming committee meetings">
      {meetings.length === 0 ? (
        source?.last_success ? (
          <DataState kind="empty">No upcoming committee meetings are on file.</DataState>
        ) : (
          <DataState kind="missing">Committee schedules haven’t loaded yet.</DataState>
        )
      ) : (
        <ol className="divide-y divide-line">
          {meetings.map((m) => {
            const flagged = m.status && m.status !== "Scheduled" ? m.status : null;
            return (
              <li
                key={m.event_id}
                className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:gap-5"
              >
                <p className="shrink-0 text-xs font-semibold tabular-nums text-ink-soft sm:w-48 sm:pt-0.5">
                  <time dateTime={m.starts_at}>{formatMeetingTime(m.starts_at) ?? "Time not published"}</time>
                </p>
                <div className="min-w-0">
                  <Link
                    href={`/committees/${m.committee_id}`}
                    className="font-semibold text-ink transition-colors hover:text-govblue-600"
                  >
                    {m.committee_name}
                  </Link>
                  {m.title && <p className="mt-0.5 line-clamp-2 text-sm text-ink-soft">{m.title}</p>}
                  {(m.chamber || m.meeting_type || flagged) && (
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
                      {[m.chamber, m.meeting_type].filter(Boolean).join(" · ")}
                      {flagged && (
                        <span className={`rounded-full border px-2 py-0.5 font-semibold ${statusTone(flagged)}`}>
                          {flagged}
                        </span>
                      )}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      <p className="mt-4 text-xs text-ink-muted">
        Eastern time, status as published. Source: {source?.publisher ?? "Congress.gov"}.
      </p>
    </Panel>
  );
}

function Legislative({ data }: { data: Overview }) {
  const { chambers, activity, sources } = data;
  const house = sumCollected(activity.votes.house);
  const senate = sumCollected(activity.votes.senate);
  const rollCalls = house === null && senate === null ? null : (house ?? 0) + (senate ?? 0);
  const asOf = formatMeetingTime(data.generated_at);

  return (
    <section id="legislative" aria-labelledby="legislative-heading" className="min-w-0 scroll-mt-24 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Legislative branch</p>
          <h2 id="legislative-heading" className="font-display text-2xl font-bold tracking-tight text-ink">
            Congress
          </h2>
          <p className="text-sm text-ink-soft">
            The {ordinal(data.congress)} Congress
            {asOf && (
              <>
                {" "}
                · as of <time dateTime={data.generated_at}>{asOf}</time>
              </>
            )}
          </p>
        </div>
        <PanelLink href="/map">Open the Congress map</PanelLink>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric
          label="Members in office"
          value={NUMBER.format(chambers.house.total + chambers.senate.total)}
          detail={`House ${NUMBER.format(chambers.house.total)} · Senate ${NUMBER.format(chambers.senate.total)}, House delegates included`}
          href="/members"
        />
        <Metric
          label="Laws enacted"
          value={NUMBER.format(data.laws_enacted)}
          detail={`Measures on file that became law in the ${ordinal(data.congress)} Congress`}
          href="/bills?status=became-law"
        />
        <Metric
          label="Measures on file"
          value={NUMBER.format(data.bills_in_congress)}
          detail="Bills and resolutions GovMap holds for this Congress, not the official total"
          href="/bills"
        />
        <Metric
          label={`Roll calls · ${activity.weeks.length} weeks`}
          value={rollCalls === null ? "—" : NUMBER.format(rollCalls)}
          detail={`House ${countOrMissing(house)} · Senate ${countOrMissing(senate)}`}
          href="/votes"
        />
      </div>

      <Panel eyebrow="Seats held now" title="Party balance">
        <div className="grid gap-8 sm:grid-cols-2">
          <Hemicycle name="House" balance={chambers.house} />
          <Hemicycle name="Senate" balance={chambers.senate} />
        </div>
        <p className="mt-4 text-xs leading-relaxed text-ink-muted">
          Members in office today, including the House’s non-voting delegates; vacant seats are not drawn.
          Independents and members of other parties are grouped together. Source:{" "}
          {sourceNamed(sources, "congress_legislators")?.publisher ?? "the congress-legislators project"}.
        </p>
      </Panel>

      <Panel eyebrow={`Last ${activity.weeks.length} weeks`} title="Weekly activity">
        <div className="grid gap-10 lg:grid-cols-2">
          <VotesChart activity={activity} publisher={sourceNamed(sources, "votes")?.publisher} />
          <BillsChart
            activity={activity}
            congress={data.congress}
            publisher={sourceNamed(sources, "congress_gov_bills")?.publisher}
          />
        </div>
      </Panel>

      <MeetingsPanel meetings={data.upcoming_meetings} source={sourceNamed(sources, "committee_meetings")} />
    </section>
  );
}

// --- Executive and Judicial (planned) -------------------------------------

function PlannedBranch({
  id,
  eyebrow,
  title,
  sources,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  sources: PlannedSource[];
  children: ReactNode;
}) {
  return (
    <Panel id={id} level={2} eyebrow={eyebrow} title={title} className="scroll-mt-24">
      <DataState kind="planned">{children}</DataState>
      <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        Planned official sources
      </h3>
      <ul className="mt-2 space-y-2 text-sm">
        {sources.map((s) => (
          <li key={s.what} className="flex items-start gap-2.5">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full border border-govblue-600" aria-hidden="true" />
            <span>
              <span className="font-semibold text-ink">{s.what}</span>
              <span className="block text-xs text-ink-muted">{s.from}</span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// --- Source freshness -----------------------------------------------------

function PipelinePanel({ sources, generatedAt }: { sources: SourceFreshness[]; generatedAt: string }) {
  const nowMs = Date.parse(generatedAt);
  const rows = sources.map((s) => ({ ...s, state: classifyFreshness(s.name, s.last_success, nowMs) }));
  const current = rows.filter((r) => r.state === "fresh").length;

  return (
    <Panel level={2} eyebrow="Pipeline status" title="Data sources" className="md:col-span-2 xl:col-span-1">
      <p className="text-sm text-ink-soft">
        <b className="tabular-nums text-ink">
          {current} of {rows.length}
        </b>{" "}
        sources are current against their refresh schedules.
      </p>
      <ul className="mt-4 divide-y divide-line">
        {rows.map((s) => (
          <li key={s.name} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-sm font-semibold leading-snug text-ink">{s.title}</p>
              <p className="text-xs text-ink-muted">{s.publisher}</p>
            </div>
            <FreshnessBadge state={s.state}>
              {s.last_success ? (
                <time dateTime={s.last_success} title={formatMeetingTime(s.last_success) ?? undefined}>
                  {formatAge(s.last_success, nowMs)}
                </time>
              ) : null}
            </FreshnessBadge>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-ink-muted">
        Every figure on GovMap comes from these public sources.{" "}
        <Link href="/about#coverage" className="font-semibold text-govblue-600 transition-colors hover:text-ink">
          What GovMap covers
        </Link>
      </p>
    </Panel>
  );
}

// --- Page -----------------------------------------------------------------

async function OverviewBody() {
  let data: Overview | null = null;
  try {
    data = await apiGet<Overview>("/api/overview");
  } catch (err) {
    console.error(err);
  }

  if (!data) {
    return (
      <DataState kind="error" title="The federal overview couldn’t load">
        GovMap’s data service didn’t respond. Please refresh in a moment.
      </DataState>
    );
  }

  return (
    <div className="grid animate-subtle-fade-in gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Legislative data={data} />
      <div className="grid content-start gap-6 md:grid-cols-2 xl:grid-cols-1">
        <PlannedBranch
          id="executive"
          eyebrow="Executive branch"
          title="The White House & agencies"
          sources={EXECUTIVE_SOURCES}
        >
          Presidential actions, agency leadership, nominations and agency spending are next. Nothing appears here
          until it comes straight from the official publisher.
        </PlannedBranch>
        <PlannedBranch id="judicial" eyebrow="Judicial branch" title="The federal courts" sources={JUDICIAL_SOURCES}>
          Courts, judges, appointments, vacancies and new opinions, each linked to the original record. No legal
          summaries or predicted outcomes.
        </PlannedBranch>
        <PipelinePanel sources={data.sources} generatedAt={data.generated_at} />
      </div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div role="status" className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <span className="sr-only">Loading the federal overview…</span>
      <div className="space-y-6">
        <LoadingBlock className="h-16" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <LoadingBlock key={i} className="h-28" />
          ))}
        </div>
        <LoadingBlock className="h-72" />
        <LoadingBlock className="h-96" />
      </div>
      <div className="grid content-start gap-6 md:grid-cols-2 xl:grid-cols-1">
        <LoadingBlock className="h-64" />
        <LoadingBlock className="h-64" />
      </div>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <main className="bg-canvas pb-20">
      <OverviewHeader />
      <div className="mx-auto max-w-7xl px-4 pt-8 sm:px-6">
        <Suspense fallback={<OverviewSkeleton />}>
          <OverviewBody />
        </Suspense>
      </div>
    </main>
  );
}
