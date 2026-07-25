import Link from "next/link";

import { ChamberSplit } from "@/components/ChamberSplit";
import { CongressExplorer } from "@/components/CongressExplorer";
import { SiteHeader } from "@/components/SiteHeader";
import { serverApiBase, type ChamberSummary, type CongressMap } from "@/lib/api";

// Rendered on demand — the backend isn't reachable during the image build, so
// prerendering would fetch a dead host.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "Congress",
  description: "Find your representatives and explore every seat in the U.S. House and Senate.",
};

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${serverApiBase()}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function LoadingSkeleton() {
  return (
    <section className="bg-slate-warm-50">
      <div className="mx-auto w-full max-w-6xl px-6 pb-16 pt-24 sm:pt-28">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 className="font-display text-2xl font-bold tracking-tight text-govnavy sm:text-3xl">
            Congress
          </h1>
          <p className="text-sm text-slate-warm-500">The map is warming up — one moment.</p>
        </div>
        <div className="-mx-6 h-[55vh] min-h-[340px] animate-pulse bg-slate-200 sm:mx-0 sm:h-[560px] sm:rounded-2xl" />
      </div>
    </section>
  );
}

export default async function CongressPage() {
  const [map, summary] = await Promise.all([
    getJSON<CongressMap>("/api/map"),
    getJSON<ChamberSummary>("/api/summary"),
  ]);

  if (!map) {
    return (
      <>
        <SiteHeader variant="app" />
        <main>
          <LoadingSkeleton />
        </main>
      </>
    );
  }

  return (
    <>
      <SiteHeader variant="app" />
      <main>
        <CongressExplorer map={map} />

        {/* Chamber balance — a compact status strip directly under the map, on the
            same surface as the map section so /congress reads as one pane. */}
        <section className="bg-slate-warm-50 pb-16 sm:pb-20">
          <div className="mx-auto w-full max-w-6xl px-6">
            <div className="mb-4 flex items-baseline justify-between gap-4">
              <h2 className="font-display text-lg font-bold text-govnavy">Party balance</h2>
              <Link
                href="/members"
                className="group inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govnavy"
              >
                Browse all members
                <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
                  →
                </span>
              </Link>
            </div>
            {summary ? (
              <ChamberSplit summary={summary} />
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="h-32 w-full animate-pulse rounded-2xl bg-slate-200" />
                <div className="h-32 w-full animate-pulse rounded-2xl bg-slate-200" />
              </div>
            )}
          </div>
        </section>
      </main>
    </>
  );
}
