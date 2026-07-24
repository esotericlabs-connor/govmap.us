import Link from "next/link";
import { Suspense } from "react";

import { chamberLabel, CodePill, EmptyState, formatDate } from "@/components/DetailKit";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet } from "@/lib/api";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Votes",
  description: "The most recent roll-call votes in the U.S. House and Senate.",
};

type VoteListItem = {
  vote_id: string;
  chamber: string;
  roll_number: number;
  date: string | null;
  question: string | null;
  result: string | null;
  bill_id: string | null;
};

function resultClass(result: string | null): string {
  if (!result) return "text-slate-warm-500";
  const r = result.toLowerCase();
  if (r.includes("pass") || r.includes("agreed") || r.includes("confirm")) return "text-green-700";
  if (r.includes("fail") || r.includes("reject") || r.includes("not")) return "text-red-700";
  return "text-slate-warm-600";
}

async function VoteList() {
  let votes: VoteListItem[] = [];
  let loadError = false;
  try {
    votes = await apiGet<VoteListItem[]>("/api/votes?limit=250");
  } catch (err) {
    console.error(err);
    loadError = true;
  }

  if (loadError) {
    return (
      <div className="mt-10 rounded-2xl border border-red-200/80 bg-red-100/50 p-8 text-center">
        <h2 className="font-semibold text-red-900">Could not load votes</h2>
        <p className="mt-2 text-red-800">Please try again in a moment.</p>
      </div>
    );
  }

  if (votes.length === 0) {
    return (
      <div className="mt-10">
        <EmptyState>No votes loaded yet.</EmptyState>
      </div>
    );
  }

  return (
    <div className="mt-10 space-y-4">
      {votes.map((v, i) => (
        <Reveal key={v.vote_id} delay={Math.min(i, 8) * 40}>
          <Link
            href={`/votes/${v.vote_id}`}
            className="group block rounded-xl border border-slate-warm-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover"
          >
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-warm-400">
              <span className="font-semibold text-slate-warm-600">
                {chamberLabel(v.chamber)} · Roll {v.roll_number}
              </span>
              {v.date && <span>· {formatDate(v.date)}</span>}
              {v.bill_id && <CodePill>{v.bill_id}</CodePill>}
            </div>
            <p className="mt-2 font-semibold text-govnavy transition-colors group-hover:text-govblue-600">
              {v.question ?? `Roll Call ${v.roll_number}`}
            </p>
            {v.result && (
              <p className={`mt-1 text-sm font-semibold ${resultClass(v.result)}`}>{v.result}</p>
            )}
          </Link>
        </Reveal>
      ))}
    </div>
  );
}

function VoteListSkeleton() {
  return (
    <div className="mt-10 space-y-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-24 w-full animate-pulse rounded-xl bg-slate-warm-200" />
      ))}
    </div>
  );
}

export default function VotesPage() {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-5xl px-6">
          <Reveal>
            <h1 className="font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
              Roll-Call Votes
            </h1>
            <p className="mt-2 text-lg text-slate-warm-600">
              The most recent recorded votes in the House and Senate.
            </p>
          </Reveal>
          <Suspense fallback={<VoteListSkeleton />}>
            <VoteList />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
