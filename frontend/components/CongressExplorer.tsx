"use client";

import Link from "next/link";
import { useMemo } from "react";

import { UsMap } from "@/components/UsMap";
import { useHomeZip } from "@/lib/zip-context";
import type { ChamberBalance, ChamberSummary, CongressMap } from "@/lib/api";

/**
 * Full-screen map "app" for /congress: the geographic map fills the viewport
 * below the header, and the party-balance stats float over it as a HUD panel
 * (a broadcast-style overlay). Global search + the "set your ZIP" affordance
 * live in the header (UniversalSearch → ZipProvider); the resolved home area
 * drives the highlight + fly-to inside UsMap, and here we only mirror it to
 * screen readers. The server page fetches /api/map + /api/summary and passes
 * them in.
 */

function HudChamber({
  label,
  chamber,
  b,
}: {
  label: string;
  chamber: "house" | "senate";
  b: ChamberBalance;
}) {
  const total = b.total || 1;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <Link
      href={`/members?chamber=${chamber}`}
      className="group block rounded-lg px-1.5 py-1 transition-colors hover:bg-white/5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-white/70">{label}</span>
        <span className="text-[11px] text-white/40">{b.total} seats</span>
      </div>
      <div
        className="mt-1.5 flex h-2 w-full overflow-hidden rounded-full bg-white/10"
        role="img"
        aria-label={`${b.D} Democrats, ${b.I} Independents, ${b.R} Republicans`}
      >
        <div className="bg-govblue" style={{ width: pct(b.D) }} />
        <div className="bg-slate-400" style={{ width: pct(b.I) }} />
        <div className="bg-govred" style={{ width: pct(b.R) }} />
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-xs font-semibold">
        <span className="text-govblue-400">D {b.D}</span>
        {b.I > 0 && <span className="text-slate-300">I {b.I}</span>}
        <span className="text-red-400">R {b.R}</span>
        <span className="ml-auto text-white/40 transition-colors group-hover:text-white/80">Browse →</span>
      </div>
    </Link>
  );
}

export function CongressExplorer({
  map,
  summary,
}: {
  map: CongressMap;
  summary: ChamberSummary | null;
}) {
  const { result } = useHomeZip();

  const announcement = useMemo(() => {
    if (!result) return "";
    const names = [...result.senators, ...result.representatives]
      .map((m) => m.official_full_name)
      .join(", ");
    return names ? `Showing your representatives: ${names}.` : "";
  }, [result]);

  return (
    <div className="relative mt-20 h-[calc(100dvh-5rem)] w-full overflow-hidden bg-slate-warm-50">
      {announcement && (
        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
      )}

      <UsMap map={map} />

      {/* HUD — party-balance stat panel (bottom-left). */}
      {summary && (
        <div className="absolute bottom-3 left-3 z-20 w-[min(19rem,calc(100%-1.5rem))] rounded-2xl border border-white/10 bg-govnavy/90 p-4 text-white shadow-2xl backdrop-blur-md">
          <div className="mb-3 flex items-center justify-between">
            <h1 className="font-display text-base font-bold">Congress · balance of power</h1>
            <Link
              href="/members"
              className="text-xs font-semibold text-govblue-400 transition-colors hover:text-white"
            >
              All →
            </Link>
          </div>
          <div className="space-y-2.5">
            <HudChamber label="The House" chamber="house" b={summary.house} />
            <HudChamber label="The Senate" chamber="senate" b={summary.senate} />
          </div>
        </div>
      )}
    </div>
  );
}
