"use client";

import { useMemo, useState } from "react";

import { CongressCartogram } from "@/components/CongressCartogram";
import { ZipLookup } from "@/components/ZipLookup";
import type { CongressMap, LookupResult } from "@/lib/api";

/**
 * Ties the ZIP lookup to the seat chart: looking up your ZIP rings your
 * senators + representative(s) on the map. Both need to share the resolved
 * result, so they live in one client component; the page fetches /api/map
 * server-side and passes it in.
 */
export function CongressExplorer({ map }: { map: CongressMap }) {
  const [result, setResult] = useState<LookupResult | null>(null);

  const highlight = useMemo(() => {
    const s = new Set<string>();
    if (result) {
      for (const m of result.senators) s.add(m.bioguide_id);
      for (const m of result.representatives) s.add(m.bioguide_id);
    }
    return s;
  }, [result]);

  return (
    <>
      {/* Hero: find-your-reps ZIP entry over the dark brand gradient. */}
      <section className="relative isolate overflow-hidden bg-govnavy">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-govnavy-800 via-govnavy to-govnavy" />
        <div className="mx-auto w-full max-w-6xl px-6 pb-14 pt-28 sm:pt-32">
          <h1 className="max-w-2xl font-display text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl">
            Find your voice in Congress.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-white/70">
            Enter your ZIP code to see exactly who represents you — then explore
            every seat in the House and Senate.
          </p>
          <div className="mt-8">
            <ZipLookup onResult={setResult} className="max-w-2xl" />
          </div>
        </div>
      </section>

      {/* The seat chart. */}
      <section className="bg-white">
        <div className="mx-auto w-full max-w-4xl px-6 py-14">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-card sm:p-8">
            <CongressCartogram map={map} highlight={highlight} />
          </div>
        </div>
      </section>
    </>
  );
}
