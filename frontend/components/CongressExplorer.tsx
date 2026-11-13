"use client";

import { useMemo } from "react";

import { UsMap } from "@/components/UsMap";
import { useHomeZip } from "@/lib/zip-context";
import type { CongressMap } from "@/lib/api";

/**
 * Full-screen map workspace: the geographic map fills the viewport
 * between the header and a slim bottom status bar (party legend + House/Senate
 * balance + local/DC time). Global search + "set your ZIP" live in the header
 * (UniversalSearch → ZipProvider); the resolved home area drives the highlight +
 * fly-to inside UsMap, and here we mirror it to screen readers. The server page
 * passes /api/map; the shared workspace chrome owns the status bar.
 */
export function CongressExplorer({
  map,
}: {
  map: CongressMap;
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
      {/* Keep map geometry above the shared bar, including device safe areas. */}
      <div
        data-workspace-focus
        tabIndex={-1}
        aria-label="Congress map"
        className="fixed inset-x-0 bottom-[var(--workspace-bar-height)] top-20 overflow-hidden bg-slate-warm-50"
      >
        {announcement && (
          <div className="sr-only" role="status" aria-live="polite">
            {announcement}
          </div>
        )}
        <UsMap map={map} />
      </div>
    </>
  );
}
