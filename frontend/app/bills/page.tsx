import Link from "next/link";
import { Suspense } from "react";

import { CodePill, EmptyState, formatDate } from "@/components/DetailKit";
import { Reveal } from "@/components/Reveal";
import { ListToolbar } from "@/components/ListToolbar";
import { ListPageLink } from "@/components/ListPageLink";
import { apiGet } from "@/lib/api";
import { readListQuery } from "@/lib/list-controls.mjs";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

type BillView = "recent" | "laws";
type BillsSearchParams = Promise<Record<string, string | string[] | undefined>>;
type BrowseQuery = ReturnType<typeof readListQuery>;

const VIEWS: Record<
  BillView,
  { tab: string; href: string; title: string; intro: string; api: string; empty: string }
> = {
  recent: {
    tab: "Recently active",
    href: "/bills",
    title: "Bills & Resolutions",
    intro: "The most recently active legislation in the current Congress.",
    api: "/api/bills?limit=250",
    empty: "No bills loaded yet.",
  },
  laws: {
    tab: "Became law",
    href: "/bills?status=became-law",
    title: "Recently enacted laws",
    intro: "Bills and joint resolutions that became law, newest action first.",
    api: "/api/bills?status=became_law&limit=250",
    empty: "No enacted laws loaded yet.",
  },
};

// Any value other than the one we know falls back to the default view.
async function resolveView(searchParams: BillsSearchParams): Promise<BillView> {
  const { status } = await searchParams;
  return status === "became-law" ? "laws" : "recent";
}

export async function generateMetadata({ searchParams }: { searchParams: BillsSearchParams }) {
  const view = await resolveView(searchParams);
  return view === "laws"
    ? {
        title: "Recently enacted laws",
        description: "Bills and joint resolutions that became law, newest action first.",
      }
    : {
        title: "Bills",
        description: "The most recently active bills and resolutions in Congress.",
      };
}

type BillListItem = {
  bill_id: string;
  bill_type: string;
  number: number;
  title: string | null;
  status: string | null;
  latest_action: string | null;
  latest_action_date: string | null;
  introduced_date: string | null;
};

async function BillList({ view, query, billType, congress }: { view: BillView; query: BrowseQuery; billType: string; congress: string }) {
  let bills: BillListItem[] = [];
  let loadError = false;
  try {
    const params = new URLSearchParams({ limit: "51", offset: String(query.offset), sort: query.sort });
    if (view === "laws") params.set("status", "became_law");
    if (query.q) params.set("q", query.q);
    if (billType) params.set("bill_type", billType);
    if (congress) params.set("congress", congress);
    bills = await apiGet<BillListItem[]>(`/api/bills?${params}`);
  } catch (err) {
    console.error(err);
    loadError = true;
  }

  if (loadError) {
    return (
      <div className="mt-10 rounded-2xl border border-red-200/80 bg-red-100/50 p-8 text-center">
        <h2 className="font-semibold text-red-900">Could not load bills</h2>
        <p className="mt-2 text-red-800">Please try again in a moment.</p>
      </div>
    );
  }

  if (bills.length === 0) {
    return (
      <div className="mt-10">
        <EmptyState>{query.q || billType || congress || query.offset ? "No stored bills match on this page. Try another search, clear the filters or return to the first page." : VIEWS[view].empty}</EmptyState>
        {query.offset > 0 && <ListPageLink className="text-sm font-semibold text-govblue-600" href={billPageHref(view, query, billType, congress, 0)}>First page</ListPageLink>}
      </div>
    );
  }

  return (
    <div className="mt-10 space-y-4">
      <p role="status" className="text-sm text-ink-muted">Records {query.offset + 1}–{query.offset + Math.min(bills.length, 50)} · searches all stored bills in this view</p>
      {bills.slice(0, 50).map((b, i) => (
        <Reveal key={b.bill_id} delay={Math.min(i, 8) * 40}>
          <Link
            href={`/bills/${b.bill_id}`}
            className="group block rounded-xl border border-slate-warm-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover"
          >
            <div className="flex flex-wrap items-center gap-3">
              <CodePill>{`${b.bill_type.toUpperCase()} ${b.number}`}</CodePill>
              {b.status && (
                <span className="rounded-full bg-slate-warm-100 px-2.5 py-0.5 text-xs font-semibold text-slate-warm-600">
                  {b.status}
                </span>
              )}
              {b.introduced_date && (
                <span className="text-xs text-slate-warm-400">
                  Introduced {formatDate(b.introduced_date)}
                </span>
              )}
              {view === "laws" && b.latest_action_date && (
                <span className="text-xs text-slate-warm-400">
                  Latest action {formatDate(b.latest_action_date)}
                </span>
              )}
            </div>
            <p className="mt-2 font-semibold text-govnavy transition-colors group-hover:text-govblue-600">
              {b.title ?? `${b.bill_type.toUpperCase()} ${b.number}`}
            </p>
            {b.latest_action && (
              <p className="mt-1 line-clamp-2 text-sm text-slate-warm-500">{b.latest_action}</p>
            )}
          </Link>
        </Reveal>
      ))}
      <nav aria-label="Bill pages" className="flex items-center gap-5 py-3 text-sm font-semibold text-govblue-600">
        {query.offset > 0 && <ListPageLink href={billPageHref(view, query, billType, congress, Math.max(0, query.offset - 50))}>Previous</ListPageLink>}
        {bills.length > 50 && <ListPageLink href={billPageHref(view, query, billType, congress, query.offset + 50)}>Next</ListPageLink>}
      </nav>
    </div>
  );
}

function billPageHref(view: BillView, query: BrowseQuery, billType: string, congress: string, offset: number): string {
  const params = new URLSearchParams({ sort: query.sort });
  if (view === "laws") params.set("status", "became-law");
  if (query.q) params.set("q", query.q);
  if (billType) params.set("bill_type", billType);
  if (congress) params.set("congress", congress);
  if (offset) params.set("offset", String(offset));
  return `/bills?${params}`;
}

function BillListSkeleton() {
  return (
    <div className="mt-10 space-y-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-24 w-full animate-pulse rounded-xl bg-slate-warm-200" />
      ))}
    </div>
  );
}

function BillViewTabs({ view }: { view: BillView }) {
  return (
    <nav
      aria-label="Bill views"
      className="inline-flex self-start rounded-full border border-slate-warm-200 bg-slate-warm-100 p-1"
    >
      {(Object.keys(VIEWS) as BillView[]).map((key) => {
        const active = key === view;
        return (
          <Link
            key={key}
            href={VIEWS[key].href}
            scroll={false}
            aria-current={active ? "page" : undefined}
            className={`rounded-full px-5 py-1.5 text-sm font-semibold transition-colors duration-300 ${
              active ? "bg-govnavy text-white shadow-md" : "text-slate-warm-600 hover:text-govnavy"
            }`}
          >
            {VIEWS[key].tab}
          </Link>
        );
      })}
    </nav>
  );
}

export default async function BillsPage({ searchParams }: { searchParams: BillsSearchParams }) {
  const view = await resolveView(searchParams);
  const params = await searchParams;
  const query = readListQuery(params, ["recent", "oldest", "title", "number"], "recent");
  const billType = typeof params.bill_type === "string" ? params.bill_type : "";
  const congress = typeof params.congress === "string" ? params.congress : "";
  const invalid = query.invalid || (!!billType && !["hr", "s", "hres", "sres", "hjres", "sjres", "hconres", "sconres"].includes(billType))
    || (!!congress && (!/^\d+$/.test(congress) || Number(congress) < 1 || Number(congress) > 1000));
  return (
    <>
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-5xl px-6">
          <Reveal>
            <div className="md:flex md:items-center md:justify-between md:gap-6">
              <div>
                <h1 className="font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
                  {VIEWS[view].title}
                </h1>
                <p className="mt-2 text-lg text-slate-warm-600">{VIEWS[view].intro}</p>
              </div>
              <div className="mt-6 shrink-0 md:mt-0">
                <BillViewTabs view={view} />
              </div>
            </div>
            {view === "laws" && (
              <p className="mt-4 max-w-3xl text-sm text-slate-warm-500">
                Enactment comes from each bill’s Congress.gov record. This list covers the bills
                GovMap has loaded in full; the rest are filled in continuously and appear here once
                their full record arrives.
              </p>
            )}
          </Reveal>
          <div className="mt-6">
            <ListToolbar
              label="Search bills"
              searchPlaceholder="Bill title, number, or action"
              searchValue={query.q}
              sortValue={query.sort}
              resetHref={VIEWS[view].href}
              sorts={[{ value: "recent", label: "Recently active" }, { value: "oldest", label: "Oldest action" }, { value: "title", label: "Title A-Z" }, { value: "number", label: "Bill number" }]}
              fields={[
                { name: "bill_type", label: "Bill type", value: billType, options: [{ value: "", label: "All types" }, ...["hr", "s", "hres", "sres", "hjres", "sjres", "hconres", "sconres"].map((value) => ({ value, label: value.toUpperCase() }))] },
                { name: "congress", label: "Congress", type: "number", min: 1, max: 1000, value: congress },
              ]}
            />
          </div>
          {invalid ? <p role="alert" className="mt-6 text-govred">Invalid list filters. Clear filters or use a supported sort, bill type and Congress.</p> : (
            <Suspense fallback={<BillListSkeleton />}>
              <BillList view={view} query={query} billType={billType} congress={congress} />
            </Suspense>
          )}
        </div>
      </main>
    </>
  );
}
