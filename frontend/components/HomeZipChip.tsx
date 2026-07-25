"use client";

import Link from "next/link";

import { useHomeZip } from "@/lib/zip-context";

/**
 * Compact "your area" pill for the app header. Once a ZIP is set it shows the
 * home district (or state/ZIP), links to the map, and offers a quick clear.
 * Renders nothing until a ZIP is set — and nothing during SSR, since the context
 * hydrates client-side (no mismatch).
 */
export function HomeZipChip() {
  const { zip, result, clearHomeZip } = useHomeZip();
  if (!zip) return null;

  const rep = result?.representatives[0];
  const label = rep
    ? rep.district && rep.district > 0
      ? `${rep.state}-${rep.district}`
      : rep.state
    : zip;

  return (
    <div className="flex items-center gap-1 rounded-full border border-white/15 bg-white/10 py-1 pl-3 pr-1 text-sm text-white/90">
      <Link
        href="/congress"
        className="flex items-center gap-1.5 font-semibold transition-colors hover:text-white"
        title={`Your area · ZIP ${zip}`}
      >
        <span aria-hidden="true">📍</span>
        {label}
      </Link>
      <button
        type="button"
        onClick={clearHomeZip}
        aria-label="Clear your area"
        className="flex h-5 w-5 items-center justify-center rounded-full text-white/50 transition-colors hover:bg-white/10 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
