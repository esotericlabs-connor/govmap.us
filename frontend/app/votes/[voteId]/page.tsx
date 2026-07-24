import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { BackLink, chamberLabel, EmptyState, formatDate, partyTextClass, Section } from "@/components/DetailKit";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type VoteDetail, type VotePosition } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getVote(voteId: string): Promise<VoteDetail | null> {
  try {
    return await apiGet<VoteDetail>(`/api/votes/${encodeURIComponent(voteId)}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: { params: { voteId: string } }) {
  const vote = await getVote(params.voteId).catch(() => null);
  return { title: vote ? `${chamberLabel(vote.chamber)} Vote ${vote.roll_number}` : "Vote" };
}

const TALLY_STYLES: Record<string, { label: string; color: string }> = {
  yea: { label: "Yea", color: "bg-green-600" },
  nay: { label: "Nay", color: "bg-red-600" },
  present: { label: "Present", color: "bg-amber-500" },
  not_voting: { label: "Not Voting", color: "bg-slate-400" },
  absent: { label: "Absent", color: "bg-slate-400" },
};

// Normalize positions for grouping (e.g. "Aye" -> "Yea").
function getPositionGroup(p: VotePosition): string {
  const pos = p.position?.trim().toLowerCase() ?? "not voting";
  if (pos === "aye") return "yea";
  if (pos === "no") return "nay";
  return pos;
}

async function VoteDetailContent({ voteId }: { voteId: string }) {
  const vote = await getVote(voteId);
  if (!vote) notFound();

  // --- Data processing ---
  const totals: Record<string, number | null> = vote.totals ?? {};
  const totalVotes = Object.values(totals).reduce<number>((sum, n) => sum + (n ?? 0), 0);
  const tallies = Object.entries(totals)
    .map(([key, n]) => ({ key, n: n || 0 }))
    .filter((t) => t.n > 0)
    .sort((a, b) => b.n - a.n);

  const groupedPositions = new Map<string, VotePosition[]>();
  for (const position of vote.positions) {
    const groupKey = getPositionGroup(position);
    if (!groupedPositions.has(groupKey)) {
      groupedPositions.set(groupKey, []);
    }
    groupedPositions.get(groupKey)?.push(position);
  }
  const positionGroups = Array.from(groupedPositions.entries()).sort(
    (a, b) => (TALLY_STYLES[b[0]] ? 1 : -1) - (TALLY_STYLES[a[0]] ? 1 : -1) || a[0].localeCompare(b[0]),
  );
  // --- End data processing ---
  return (
    <Reveal>
      <header className="mt-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-warm-500">
          <span className="font-semibold text-base">
            {chamberLabel(vote.chamber)} · Roll Call {vote.roll_number}
          </span>
          {vote.date && <span>· {formatDate(vote.date)}</span>}
          {vote.bill_id && (
            <Link
              href={`/bills/${vote.bill_id}`}
              className="font-mono font-medium text-govblue transition-colors hover:text-govblue-600 hover:underline"
            >
              {vote.bill_id}
            </Link>
          )}
        </div>
        <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
          {vote.question ?? `On the matter of: ${vote.bill_id ?? "Procedural Vote"}`}
        </h1>
        <p
          className={`mt-4 text-xl font-bold ${
            vote.result === "Passed" ? "text-green-700" : "text-red-700"
          }`}
        >
          Result: {vote.result}
        </p>
        {vote.source_url && (
          <a
            href={vote.source_url}
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-block text-sm font-semibold text-govblue transition-colors hover:text-govblue-600"
          >
            Official Record ↗
          </a>
        )}
      </header>

      <div className="mt-12 space-y-10">
        {/* Vote tally bar */}
        {tallies.length > 0 && totalVotes > 0 && (
          <Section title="Result">
            <div className="space-y-4">
              <div
                className="flex h-3 w-full overflow-hidden rounded-full bg-slate-warm-200"
                role="img"
                aria-label="Vote tally bar"
              >
                {tallies.map(({ key, n }) => (
                  <div
                    key={key}
                    className={TALLY_STYLES[key]?.color ?? "bg-slate-300"}
                    style={{ width: `${(n / totalVotes) * 100}%` }}
                    title={`${TALLY_STYLES[key]?.label}: ${n}`}
                  />
                ))}
              </div>
              <div className="flex flex-wrap justify-center gap-x-8 gap-y-3">
                {tallies.map(({ key, n }) => (
                  <div key={key} className="flex items-center gap-2">
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${
                        TALLY_STYLES[key]?.color ?? "bg-slate-300"
                      }`}
                    />
                    <span className="text-sm font-medium text-slate-warm-700">
                      {TALLY_STYLES[key]?.label ?? key}:{" "}
                      <span className="font-bold text-govnavy">{n}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Section>
        )}

        {/* Per-member votes */}
        {positionGroups.map(([groupKey, positions]) => (
          <div key={groupKey}>
            <Section title={TALLY_STYLES[groupKey]?.label ?? groupKey} count={positions.length}>
              {positions.length === 0 ? (
                <EmptyState>No members voted {groupKey}.</EmptyState>
              ) : (
                <ul className="grid grid-cols-1 gap-x-8 gap-y-3 pt-2 md:grid-cols-2 xl:grid-cols-3">
                  {positions.map((p) => (
                    <li key={p.bioguide_id}>
                      <Link
                        href={`/members/${p.bioguide_id}`}
                        className="group inline-flex min-w-0 items-baseline gap-2 text-sm"
                      >
                        <span className="font-semibold text-slate-800 transition-colors group-hover:text-govblue">
                          {p.official_full_name}
                        </span>
                        <span
                          className={`flex-shrink-0 font-medium ${partyTextClass(p.party)}`}
                        >
                          ({p.party?.slice(0, 1)}-{p.state})
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        ))}
      </div>
    </Reveal>
  );
}

export default function VoteDetailPage({ params }: { params: { voteId: string } }) {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-6xl px-6">
          <BackLink href="/votes">All Votes</BackLink>
          <Suspense fallback={<PageSkeleton />}>
            <VoteDetailContent voteId={params.voteId} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
