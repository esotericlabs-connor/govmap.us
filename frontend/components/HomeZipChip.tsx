"use client";

import Link from "next/link";

import { useHomeZip } from "@/lib/zip-context";

const TONES = {
  bar: {
    chip: "border-slate-warm-300 bg-slate-warm-50 text-govnavy",
    link: "hover:text-govblue-600",
    clear: "text-slate-warm-500 hover:bg-slate-warm-200 hover:text-govnavy",
  },
  chrome: {
    chip: "border-white/15 bg-white/10 text-white/90",
    link: "hover:text-white",
    clear: "text-white/50 hover:bg-white/10 hover:text-white",
  },
} as const;

/**
 * Compact "your area" pill for the app header. Once a ZIP is set it shows the
 * home district (or state/ZIP), links to the map, and offers a quick clear.
 * Renders nothing until a ZIP is set — and nothing during SSR, since the context
 * hydrates client-side (no mismatch). "chrome" is for the always-navy menu blade.
 */
export function HomeZipChip({ tone = "bar" }: { tone?: keyof typeof TONES }) {
  const { zip, result, clearHomeZip } = useHomeZip();
  if (!zip) return null;

  const t = TONES[tone];
  const rep = result?.representatives[0];
  const label = rep
    ? rep.district && rep.district > 0
      ? `${rep.state}-${rep.district}`
      : rep.state
    : zip;

  return (
    <div className={`flex items-center gap-1 rounded-full border py-1 pl-3 pr-1 text-sm ${t.chip}`}>
      <Link
        href="/map"
        className={`flex items-center gap-1.5 font-semibold transition-colors ${t.link}`}
        title={`Your area · ZIP ${zip}`}
      >
        <span aria-hidden="true">📍</span>
        {label}
      </Link>
      <button
        type="button"
        onClick={clearHomeZip}
        aria-label="Clear your area"
        className={`flex h-5 w-5 items-center justify-center rounded-full transition-colors ${t.clear}`}
      >
        ✕
      </button>
    </div>
  );
}
