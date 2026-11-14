/**
 * Data-state primitives. The dashboard never shows an empty chart or a bare
 * zero without saying which of these it is: a true zero, records GovMap does
 * not collect, partial coverage, stale data, a failed source, or a source
 * that is planned but not yet integrated.
 */

import type { ReactNode } from "react";

import type { Freshness } from "@/lib/freshness.mjs";

export type DataStateKind = "empty" | "missing" | "partial" | "stale" | "error" | "planned";

const STATES: Record<DataStateKind, { label: string; tone: string }> = {
  empty: { label: "None recorded", tone: "border-line bg-sunken text-ink-soft" },
  missing: { label: "Not collected", tone: "border-dashed border-line bg-panel text-ink-soft" },
  partial: { label: "Partial coverage", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  stale: { label: "Data may be out of date", tone: "border-amber-200 bg-amber-50 text-amber-900" },
  error: { label: "Source unavailable", tone: "border-red-200 bg-red-50 text-red-900" },
  planned: {
    label: "Not yet integrated",
    tone: "border-dashed border-govblue-400 bg-govblue-100/40 text-ink-soft",
  },
};

export function DataState({
  kind,
  title,
  children,
}: {
  kind: DataStateKind;
  title?: ReactNode;
  children?: ReactNode;
}) {
  const state = STATES[kind];
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${state.tone}`}>
      <p className="font-semibold">{title ?? state.label}</p>
      {children && <div className="mt-1 leading-relaxed">{children}</div>}
    </div>
  );
}

/** Placeholder block while a server section streams in. */
export function LoadingBlock({ className = "h-40" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-2xl bg-sunken motion-reduce:animate-none ${className}`}
      aria-hidden="true"
    />
  );
}

const FRESHNESS: Record<Freshness, { dot: string; label: string }> = {
  fresh: { dot: "bg-green-500", label: "Current" },
  stale: { dot: "bg-amber-500", label: "Stale" },
  never: { dot: "bg-slate-400", label: "Not yet loaded" },
};

/** A status dot plus its word, so the state never depends on color alone. */
export function FreshnessBadge({ state, children }: { state: Freshness; children?: ReactNode }) {
  const f = FRESHNESS[state];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-ink-soft">
      <span className={`h-2 w-2 shrink-0 rounded-full ${f.dot}`} aria-hidden="true" />
      <span className="font-semibold text-ink">{f.label}</span>
      {children && <span>· {children}</span>}
    </span>
  );
}
