import Link from "next/link";
import { Suspense } from "react";

import { CodePill, EmptyState, formatDate } from "@/components/DetailKit";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { apiGet } from "@/lib/api";

// Rendered on demand — the backend isn't reachable during the image build.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Bills",
  description: "The most recently active bills and resolutions in Congress.",
};

type BillListItem = {
  bill_id: string;
  bill_type: string;
  number: number;
  title: string | null;
  status: string | null;
  latest_action: string | null;
  introduced_date: string | null;
};

async function BillList() {
  let bills: BillListItem[] = [];
  let loadError = false;
  try {
    bills = await apiGet<BillListItem[]>("/api/bills?limit=250");
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
        <EmptyState>No bills loaded yet.</EmptyState>
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

export default function BillsPage() {
  return (
    <>
      <SiteHeader variant="app" />
      <main className="bg-slate-warm-50 pb-20 pt-28">
        <div className="mx-auto max-w-5xl px-6">
          <Reveal>
            <h1 className="font-display text-4xl font-bold tracking-tight text-govnavy sm:text-5xl">
              Bills &amp; Resolutions
            </h1>
            <p className="mt-2 text-lg text-slate-warm-600">
              The most recently active legislation in the current Congress.
            </p>
          </Reveal>
          <Suspense fallback={<BillListSkeleton />}>
            <BillList />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
