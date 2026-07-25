"use client";

import { useMemo } from "react";

import { UsMap } from "@/components/UsMap";
import { useHomeZip } from "@/lib/zip-context";
import type { CongressMap } from "@/lib/api";

/**
 * The geographic map is the centerpiece of /congress. Global search + the "set
 * your ZIP" affordance now live in the header (UniversalSearch → ZipProvider),
 * so this page no longer carries its own ZIP hero; the resolved home area drives
 * the highlight + fly-to inside UsMap, and here we only mirror it to screen
 * readers. The server page fetches /api/map and passes it in.
 */
export function CongressExplorer({ map }: { map: CongressMap }) {
  const { result } = useHomeZip();

  const announcement = useMemo(() => {
    if (!result) return "";
    const names = [...result.senators, ...result.representatives]
      .map((m) => m.official_full_name)
      .join(", ");
    return names ? `Showing your representatives: ${names}.` : "";
  }, [result]);

  return (
    <section className="bg-slate-warm-50">
      <div className="mx-auto w-full max-w-6xl px-6 pb-6 pt-24 sm:pt-28">
        {announcement && (
          <div className="sr-only" role="status" aria-live="polite">
            {announcement}
          </div>
        )}
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h1 className="font-display text-2xl font-bold tracking-tight text-govnavy sm:text-3xl">
            Congress
          </h1>
          <p className="text-sm text-slate-warm-500">
            Tap your district — or set your ZIP in the search bar above to find your reps.
          </p>
        </div>
        {/* Full-bleed on mobile (cancel the parent px-6), a framed card on ≥sm. */}
        <div className="-mx-6 border-y border-slate-warm-200 bg-white p-3 shadow-sm sm:mx-0 sm:rounded-2xl sm:border sm:p-6 sm:shadow-card">
          <UsMap map={map} />
        </div>
      </div>
    </section>
  );
}
