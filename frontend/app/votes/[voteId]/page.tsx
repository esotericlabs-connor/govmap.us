import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BackLink,
  chamberLabel,
  CodePill,
  EmptyState,
  formatDate,
  partyTextClass,
  PositionPill,
  Section,
} from "@/components/DetailKit";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet, HttpError, type VoteDetail } from "@/lib/api";

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

const TALLY_LABELS: Record<string, string> = {
  yea: "Yea",
  nay: "Nay",
  present: "Present",
  not_voting: "Not voting",
  absent: "Absent",
};

export default async function VoteDetailPage({ params }: { params: { voteId: string } }) {
  const vote = await getVote(params.voteId);
  if (!vote) notFound();

  const totals: Record<string, number | null> = vote.totals ?? {};
  const tallies = Object.entries(totals).filter(([, n]) => n !== null && n !== undefined);

  return (
    <>
      <SiteHeader variant="app" />
      <main className="min-h-screen bg-slate-50 pb-16 pt-24">
        <div className="mx-auto max-w-4xl px-6 py-6">
          <BackLink href="/members">Back</BackLink>

          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-card">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="font-semibold text-slate-500">
                {chamberLabel(vote.chamber)} · Roll {vote.roll_number}
              </span>
              {vote.date && <span>· {formatDate(vote.date)}</span>}
              {vote.bill_id && (
                <Link href={`/bills/${vote.bill_id}`} className="hover:underline">
                  <CodePill>{vote.bill_id}</CodePill>
                </Link>
              )}
            </div>
            <h1 className="mt-2 font-display text-2xl font-bold text-govnavy">
              {vote.question ?? `Roll call ${vote.roll_number}`}
            </h1>
            {vote.result && (
              <p className="mt-2 text-sm font-semibold text-slate-700">{vote.result}</p>
            )}

            {tallies.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-3 border-t border-slate-100 pt-5">
                {tallies.map(([key, n]) => (
                  <div
                    key={key}
                    className="min-w-[72px] rounded-lg bg-slate-50 px-3 py-2 text-center"
                  >
                    <div className="text-xl font-bold text-govnavy">{n}</div>
                    <div className="text-xs text-slate-400">{TALLY_LABELS[key] ?? key}</div>
                  </div>
                ))}
              </div>
            )}

            {vote.source_url && (
              <a
                href={vote.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-block text-xs text-govblue hover:underline"
              >
                Official record ↗
              </a>
            )}
          </div>

          <div className="mt-6">
            <Section title="How each member voted" count={vote.positions.length}>
              {vote.positions.length === 0 ? (
                <EmptyState>No positions loaded for this vote.</EmptyState>
              ) : (
                <ul className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
                  {vote.positions.map((p) => (
                    <li key={p.bioguide_id} className="flex items-center justify-between gap-2">
                      {p.official_full_name ? (
                        <Link
                          href={`/members/${p.bioguide_id}`}
                          className={`truncate text-sm hover:underline ${partyTextClass(p.party)}`}
                        >
                          {p.official_full_name}
                          {p.state && <span className="text-slate-400"> · {p.state}</span>}
                        </Link>
                      ) : (
                        <span className="truncate text-sm text-slate-400">{p.bioguide_id}</span>
                      )}
                      <PositionPill position={p.position} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
