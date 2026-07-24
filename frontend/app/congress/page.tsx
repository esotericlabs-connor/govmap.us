import Link from "next/link";

import { ChamberSplit } from "@/components/ChamberSplit";
import { CongressExplorer } from "@/components/CongressExplorer";
import { Reveal } from "@/components/Reveal";
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

function LoadingSkeleton() {
  return (
    <>
      <section className="relative isolate overflow-hidden bg-govnavy">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-govnavy-800 via-govnavy to-govnavy" />
        <div className="mx-auto w-full max-w-6xl px-6 pb-16 pt-32 sm:pb-20 sm:pt-40">
          <div className="max-w-2xl">
            <h1 className="font-display text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl lg:text-6xl">
              Find your voice in Congress.
            </h1>
            <p className="mt-4 max-w-xl text-lg text-white/80 sm:text-xl">
              The seat chart is warming up — please check back in a moment.
            </p>
          </div>
        </div>
      </section>
      <section className="bg-slate-warm-50">
        <div className="mx-auto w-full max-w-5xl px-6 py-16 sm:py-20">
          <div className="h-96 w-full animate-pulse rounded-2xl bg-slate-200" />
        </div>
      </section>
    </>
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
        <SiteFooter />
      </>
    );
  }

  return (
    <>
      <SiteHeader variant="app" />
      <main>
        <CongressExplorer map={map} />

        {/* House vs Senate split */}
        <section className="bg-slate-warm-100">
          <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-20">
            <Reveal>
              <h2 className="font-display text-3xl font-bold tracking-tight text-govnavy sm:text-4xl">
                The two chambers
              </h2>
              <p className="mt-3 max-w-2xl text-lg text-slate-warm-600">
                Congress is composed of two chambers with distinct roles.
                Here&apos;s a look at the current party balance in each.
              </p>
            </Reveal>
            <div className="mt-10">
              {summary ? (
                <ChamberSplit summary={summary} />
              ) : (
                <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div className="h-64 w-full animate-pulse rounded-2xl bg-slate-200" />
                  <div className="h-64 w-full animate-pulse rounded-2xl bg-slate-200" />
                </div>
              )}
            </div>
            <Reveal className="mt-12 text-center">
              <Link
                href="/members"
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-7 py-3 font-semibold text-govnavy shadow-sm transition-all hover:-translate-y-px hover:border-govblue hover:text-govblue hover:shadow-md"
              >
                Browse all members
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </Link>
            </Reveal>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
