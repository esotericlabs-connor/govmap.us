"use client";

import { useMemo, useState } from "react";

import { Reveal } from "@/components/Reveal";
import { UsMap } from "@/components/UsMap";
import { ZipLookup } from "@/components/ZipLookup";
import type { CongressMap, LookupResult } from "@/lib/api";

/**
 * Ties the ZIP lookup to the geographic map: looking up your ZIP rings your
 * district + state. Both need to share the resolved result, so they live in one
 * client component; the page fetches /api/map server-side and passes it in.
 */
export function CongressExplorer({ map }: { map: CongressMap }) {
  const [result, setResult] = useState<LookupResult | null>(null);

  const highlightAnnouncement = useMemo(() => {
    if (!result || (result.senators.length === 0 && result.representatives.length === 0)) {
      return "No representatives found for that ZIP code.";
    }
    const names = [...result.senators, ...result.representatives]
      .map((m) => m.official_full_name)
      .join(", ");
    return `Found and highlighted representatives: ${names}.`;
  }, [result]);

  return (
    <>
      {/* Hero: find-your-reps ZIP entry over the dark brand gradient. */}
      <section className="relative isolate overflow-hidden bg-govnavy">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-govnavy-800 via-govnavy to-govnavy" />
        <div className="mx-auto w-full max-w-6xl px-6 pb-16 pt-32 sm:pb-20 sm:pt-40">
          <div className="max-w-2xl">
            <h1 className="font-display text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl lg:text-6xl">
              Find your voice in Congress.
            </h1>
            <p className="mt-4 max-w-xl text-lg text-white/80 sm:text-xl">
              Enter your ZIP code to see exactly who represents you, then
              explore every seat in the House and Senate.
            </p>
            <div className="mt-10">
              <ZipLookup onResult={setResult} />
            </div>
          </div>
        </div>
      </section>

      {/* The geographic map (falls back to the seat chart if geometry is absent). */}
      <section className="bg-slate-warm-50">
        <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-20">
          <Reveal>
            <div className="rounded-2xl border border-slate-warm-200 bg-white p-6 shadow-card sm:p-8">
              {/* Announce ZIP results to screen readers */}
              {result && (
                <div className="sr-only" role="status" aria-live="polite">
                  {highlightAnnouncement}
                </div>
              )}
              <UsMap map={map} result={result} />
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
