import Link from "next/link";
import { Suspense } from "react";

import { chamberLabel, CodePill, EmptyState, formatDate } from "@/components/DetailKit";
import { Reveal } from "@/components/Reveal";
import { ListToolbar } from "@/components/ListToolbar";
import { ListPageLink } from "@/components/ListPageLink";
import { apiGet } from "@/lib/api";
import { readListQuery } from "@/lib/list-controls.mjs";

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

type BrowseQuery = ReturnType<typeof readListQuery>;

function votePageHref(query: BrowseQuery, chamber: string, congress: string, offset: number): string {
  const params = new URLSearchParams({ sort: query.sort });
  if (query.q) params.set("q", query.q);
  if (chamber) params.set("chamber", chamber);
  if (congress) params.set("congress", congress);
  if (offset) params.set("offset", String(offset));
  return `/votes?${params}`;
}

async function VoteList({ query, chamber, congress }: { query: BrowseQuery; chamber: string; congress: string }) {
  let votes: VoteListItem[] = [];
  let loadError = false;
  try {
    const params = new URLSearchParams({ limit: "51", sort: query.sort, offset: String(query.offset) });
    if (query.q) params.set("q", query.q);
    if (chamber) params.set("chamber", chamber);
    if (congress) params.set("congress", congress);
    votes = await apiGet<VoteListItem[]>(`/api/votes?${params}`);
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
        <EmptyState>No stored votes match on this page. Try another search, clear the filters or return to the first page.</EmptyState>
        {query.offset > 0 && <ListPageLink className="text-sm font-semibold text-govblue-600" href={votePageHref(query, chamber, congress, 0)}>First page</ListPageLink>}
      </div>
    );
  }

  return (
    <div className="mt-10 space-y-4">
      <p role="status" className="text-sm text-ink-muted">Records {query.offset + 1}–{query.offset + Math.min(votes.length, 50)} · searches all stored votes</p>
      {votes.slice(0, 50).map((v, i) => (
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
      <nav aria-label="Vote pages" className="flex items-center gap-5 py-3 text-sm font-semibold text-govblue-600">
        {query.offset > 0 && <ListPageLink href={votePageHref(query, chamber, congress, Math.max(0, query.offset - 50))}>Previous</ListPageLink>}
        {votes.length > 50 && <ListPageLink href={votePageHref(query, chamber, congress, query.offset + 50)}>Next</ListPageLink>}
      </nav>
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

export default async function VotesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const query = readListQuery(params, ["recent", "oldest", "question"], "recent");
  const chamber = typeof params.chamber === "string" ? params.chamber : "";
  const congress = typeof params.congress === "string" ? params.congress : "";
  const invalid = query.invalid || (!!chamber && chamber !== "house" && chamber !== "senate")
    || (!!congress && (!/^\d+$/.test(congress) || Number(congress) < 1 || Number(congress) > 1000));
  return (
    <>
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
          <div className="mt-6">
            <ListToolbar
              label="Search votes"
              searchPlaceholder="Question, bill ID, or result"
              searchValue={query.q}
              sortValue={query.sort}
              sorts={[{ value: "recent", label: "Newest first" }, { value: "oldest", label: "Oldest first" }, { value: "question", label: "Question A-Z" }]}
              fields={[
                { name: "chamber", label: "Chamber", value: chamber, options: [{ value: "", label: "Both chambers" }, { value: "house", label: "House" }, { value: "senate", label: "Senate" }] },
                { name: "congress", label: "Congress", type: "number", min: 1, max: 1000, value: congress },
              ]}
            />
          </div>
          {invalid ? <p role="alert" className="mt-6 text-govred">Invalid list filters. Clear filters or use a supported sort, chamber and Congress.</p> : (
            <Suspense fallback={<VoteListSkeleton />}>
              <VoteList query={query} chamber={chamber} congress={congress} />
            </Suspense>
          )}
        </div>
      </main>
    </>
  );
}
