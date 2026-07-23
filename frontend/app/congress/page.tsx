import Link from "next/link";

import { ChamberSplit } from "@/components/ChamberSplit";
import { CongressExplorer } from "@/components/CongressExplorer";
import { SiteFooter } from "@/components/SiteFooter";
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

export default async function CongressPage() {
  const [map, summary] = await Promise.all([
    getJSON<CongressMap>("/api/map"),
    getJSON<ChamberSummary>("/api/summary"),
  ]);

  return (
    <>
      <SiteHeader variant="app" />
      <main>
        {map ? (
          <CongressExplorer map={map} />
        ) : (
          <section className="bg-govnavy px-6 pb-16 pt-32">
            <div className="mx-auto max-w-6xl">
              <h1 className="font-display text-4xl font-bold text-white">Congress</h1>
              <p className="mt-4 text-white/70">
                The seat chart is warming up — please refresh in a moment.
              </p>
            </div>
          </section>
        )}

        {/* House vs Senate split */}
        <section className="bg-slate-50">
          <div className="mx-auto w-full max-w-6xl px-6 py-16">
            <h2 className="font-display text-2xl font-bold tracking-tight text-govnavy sm:text-3xl">
              The two chambers
            </h2>
            <p className="mt-2 max-w-2xl text-slate-600">
              Congress is split into two chambers with distinct roles. Here&apos;s
              how each is composed today.
            </p>
            <div className="mt-8">
              {summary ? (
                <ChamberSplit summary={summary} />
              ) : (
                <p className="text-slate-400">Chamber balance is loading.</p>
              )}
            </div>
            <div className="mt-10">
              <Link
                href="/members"
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-6 py-3 font-semibold text-govnavy transition hover:border-govblue hover:text-govblue"
              >
                View all members →
              </Link>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
