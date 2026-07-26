"use client";

import { useMemo } from "react";

import { MapStatusBar } from "@/components/MapStatusBar";
import { UsMap } from "@/components/UsMap";
import { useHomeZip } from "@/lib/zip-context";
import type { ChamberSummary, CongressMap } from "@/lib/api";

/**
 * Full-screen map "app" for /congress: the geographic map fills the viewport
 * between the header and a slim bottom status bar (party legend + House/Senate
 * balance + local/DC time). Global search + "set your ZIP" live in the header
 * (UniversalSearch → ZipProvider); the resolved home area drives the highlight +
 * fly-to inside UsMap, and here we mirror it to screen readers. The server page
 * passes /api/map + /api/summary.
 */
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
    <>
      {/* Map fills the space between the header (top-20) and the status bar
          (bottom-9), pinned to the viewport so scroll position can't shift it. */}
      <div className="fixed inset-x-0 bottom-9 top-20 overflow-hidden bg-slate-warm-50">
        {announcement && (
          <div className="sr-only" role="status" aria-live="polite">
            {announcement}
          </div>
        )}
        <UsMap map={map} />
      </div>
      <MapStatusBar summary={summary} />
    </>
  );
}
