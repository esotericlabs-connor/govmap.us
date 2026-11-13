import Link from "next/link";

import { DataState, FreshnessBadge } from "@/components/dashboard/DataState";
import { Metric, Panel } from "@/components/dashboard/Panel";
import { PageBanner } from "@/components/PageBanner";
import { apiGet, type SourcesStatus, type SourceStatus } from "@/lib/api";
import {
  cadenceHours,
  classifyFreshness,
  describeCadence,
  formatAge,
  formatHours,
  parseFreshnessReferenceTime,
  staleAfterHours,
  type Freshness,
} from "@/lib/freshness.mjs";
import { formatMeetingTime } from "@/lib/format";
import { siteConfig } from "@/lib/site-config";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Data pipeline status",
  description:
    "Every public source GovMap loads, who publishes it, how often it refreshes and when it last refreshed successfully.",
};

// Pinned to the deployed commit so the link always matches the code serving
// this page; omitted when the build carries no commit (local builds).
function registerUrl(): string | null {
  const sha = process.env.APP_COMMIT_SHA;
  if (!sha || !/^[a-f0-9]{40}$/.test(sha)) return null;
  return `${siteConfig.githubUrl}/blob/${sha}/docs/source-coverage-register.md`;
}

const linkClass = "font-semibold text-govblue-600 underline-offset-2 transition-colors hover:text-ink hover:underline";
const termClass = "text-[11px] font-semibold uppercase tracking-wider text-ink-muted";

type Row = SourceStatus & { state: Freshness };

function SourceCard({ source, nowMs }: { source: Row; nowMs: number }) {
  const exact = source.last_success ? formatMeetingTime(source.last_success) : null;
  return (
    <li className="flex flex-col rounded-2xl border border-line bg-panel p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="font-display text-base font-bold leading-snug text-ink">{source.title}</h3>
          <p className="mt-0.5 text-sm text-ink-soft">{source.publisher}</p>
        </div>
        <FreshnessBadge state={source.state}>
          {source.last_success ? (
            <time dateTime={source.last_success} title={exact ?? undefined}>
              {formatAge(source.last_success, nowMs)}
            </time>
          ) : null}
        </FreshnessBadge>
      </div>

      <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className={termClass}>Refreshes</dt>
          <dd className="mt-0.5 text-ink">{describeCadence(source.name)}</dd>
        </div>
        <div>
          <dt className={termClass}>Last success</dt>
          <dd className="mt-0.5 text-ink">{exact ?? "Not yet loaded"}</dd>
        </div>
        <div>
          <dt className={termClass}>Marked stale after</dt>
          <dd className="mt-0.5 text-ink">{formatHours(staleAfterHours(cadenceHours(source.name)))}</dd>
        </div>
      </dl>

      <div className="mt-auto pt-4">
        <div className="border-t border-line pt-3">
          <p className={termClass}>
            Fetched from · {source.requires_key ? "publisher API key required" : "open access, no key"}
          </p>
          <ul className="mt-2 space-y-1.5">
            {source.endpoints.map((e) => (
              <li key={e.url} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <span
                  className={`rounded-full border px-2 py-0.5 font-semibold ${
                    e.official
                      ? "border-green-200 bg-green-50 text-green-800"
                      : "border-line bg-sunken text-ink-soft"
                  }`}
                >
                  {e.official ? "Official" : "Community-maintained"}
                </span>
                <code className="break-all text-ink-soft">{e.url}</code>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </li>
  );
}

async function StatusBody() {
  let response: { data: SourcesStatus; nowMs: number } | null = null;
  try {
    const data = await apiGet<SourcesStatus>("/api/sources");
    response = { data, nowMs: parseFreshnessReferenceTime(data.generated_at) };
  } catch (err) {
    console.error(err);
  }

  if (!response) {
    return (
      <DataState kind="error" title="Source status couldn’t load">
        GovMap’s data service didn’t respond or returned incomplete status information. Please refresh in a moment.
      </DataState>
    );
  }

  const { data, nowMs } = response;
  const rows: Row[] = data.sources.map((s) => ({ ...s, state: classifyFreshness(s.name, s.last_success, nowMs) }));
  const count = (state: Freshness) => rows.filter((r) => r.state === state).length;
  const officialOnly = rows.filter((r) => r.endpoints.every((e) => e.official)).length;
  const asOf = formatMeetingTime(data.generated_at);
  const register = registerUrl();

  return (
    <div className="space-y-10">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Current" value={`${count("fresh")} of ${rows.length}`} detail="Within their refresh schedule" />
        <Metric label="Stale" value={count("stale")} detail="Missed at least two scheduled refreshes" />
        <Metric label="Not yet loaded" value={count("never")} detail="No successful refresh on record" />
        <Metric
          label="Official publishers only"
          value={`${officialOnly} of ${rows.length}`}
          detail="Fetched solely from the government body that produces the record"
        />
      </div>

      <section aria-labelledby="sources-heading">
        <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
          <h2 id="sources-heading" className="font-display text-2xl font-bold tracking-tight text-ink">
            Sources
          </h2>
          {asOf && (
            <p className="text-sm text-ink-soft">
              As of <time dateTime={data.generated_at}>{asOf}</time>
            </p>
          )}
        </div>
        <ul className="mt-4 grid gap-4 lg:grid-cols-2">
          {rows.map((s) => (
            <SourceCard key={s.name} source={s} nowMs={nowMs} />
          ))}
        </ul>
      </section>

      <Panel level={2} eyebrow="How to read this page" title="What “current” means">
        <div className="space-y-3 text-sm leading-relaxed text-ink-soft">
          <p>
            A source is <b className="text-ink">current</b> while its last successful refresh is recent enough for its
            schedule. It turns <b className="text-ink">stale</b> after missing two scheduled refreshes, and never sooner
            than six hours past schedule, so a single slow run doesn’t raise a flag. Current means GovMap’s copy is up
            to date with the publisher, not that the publisher has released every record.
          </p>
          <p>
            Some records, such as a bill’s full text or a member’s itemized contributions, are fetched from these same
            publishers when you open them, so they aren’t listed separately. Run errors and internal diagnostics stay
            private; only the time of each successful refresh is published.
          </p>
          <p>
            <Link href="/about#coverage" className={linkClass}>
              What GovMap covers
            </Link>
            {" · "}
            {register && (
              <>
                <a href={register} target="_blank" rel="noreferrer" className={linkClass}>
                  Full source and coverage register
                </a>
                {" · "}
              </>
            )}
            <Link href="/security" className={linkClass}>
              Security &amp; transparency
            </Link>
          </p>
        </div>
      </Panel>
    </div>
  );
}

export default function StatusPage() {
  return (
    <main className="bg-canvas pb-20">
      <PageBanner eyebrow="Data pipeline status" title="Where every number comes from">
        Every figure on GovMap is loaded from a public source on a fixed schedule. This page lists each one, who
        publishes it, and when GovMap last refreshed it successfully.
      </PageBanner>
      <div className="mx-auto max-w-6xl px-6 pt-10">
        <StatusBody />
      </div>
    </main>
  );
}
