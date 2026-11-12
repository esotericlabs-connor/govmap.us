import Link from "next/link";
import { Suspense } from "react";

import { CodePill, EmptyState, formatDate } from "@/components/DetailKit";
import { Reveal } from "@/components/Reveal";
import { apiGet } from "@/lib/api";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

type BillView = "recent" | "laws";
type BillsSearchParams = Promise<{ status?: string | string[] }>;

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

async function BillList({ view }: { view: BillView }) {
  let bills: BillListItem[] = [];
  let loadError = false;
  try {
    bills = await apiGet<BillListItem[]>(VIEWS[view].api);
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
        <EmptyState>{VIEWS[view].empty}</EmptyState>
      </div>
    );
  }

  return (
    <div className="mt-10 space-y-4">
      {bills.map((b, i) => (
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
    </div>
  );
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
          <Suspense key={view} fallback={<BillListSkeleton />}>
            <BillList view={view} />
          </Suspense>
        </div>
      </main>
    </>
  );
}
