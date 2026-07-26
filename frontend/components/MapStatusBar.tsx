"use client";

import { useEffect, useState } from "react";

import type { ChamberSummary } from "@/lib/api";

function timeIn(d: Date, tz?: string): string {
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: tz,
    timeZoneName: "short",
  });
}

/**
 * Slim status bar pinned to the bottom of the map app: the party legend +
 * House/Senate balance, plus the viewer's local time (from their browser
 * timezone, which tracks their location — no IP lookup needed) and Washington,
 * DC time. The clock is client-only, so it starts null (SSR-safe) and ticks in.
 */
export function MapStatusBar({ summary }: { summary: ChamberSummary | null }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 flex h-9 items-center justify-between gap-4 border-t border-white/10 bg-govnavy-800/95 px-4 text-xs text-white/70 backdrop-blur">
      <div className="flex min-w-0 items-center gap-4 overflow-hidden">
        <span className="flex shrink-0 items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-govblue" />
          Democrat
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-govred" />
          Republican
        </span>
        {summary && (
          <>
            <span className="hidden text-white/20 md:inline">|</span>
            <span className="hidden shrink-0 items-center gap-1.5 md:flex">
              <span className="font-semibold uppercase tracking-wider text-white/45">House</span>
              <span className="font-semibold text-govblue-400">{summary.house.D}</span>
              <span className="text-white/30">·</span>
              <span className="font-semibold text-red-400">{summary.house.R}</span>
            </span>
            <span className="hidden shrink-0 items-center gap-1.5 md:flex">
              <span className="font-semibold uppercase tracking-wider text-white/45">Senate</span>
              <span className="font-semibold text-govblue-400">{summary.senate.D}</span>
              <span className="text-white/30">·</span>
              <span className="font-semibold text-red-400">{summary.senate.R}</span>
            </span>
          </>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2 tabular-nums text-white/60 sm:gap-3">
        {now && (
          <>
            <span className="hidden sm:inline">Local {timeIn(now)}</span>
            <span className="sm:hidden">{timeIn(now)}</span>
            <span className="text-white/20">|</span>
            <span>Washington {timeIn(now, "America/New_York")}</span>
          </>
        )}
      </div>
    </div>
  );
}
