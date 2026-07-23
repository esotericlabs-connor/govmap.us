/**
 * Shared presentational primitives + formatting helpers for the detail pages
 * (member / bill / vote / committee). Pure server-safe components — no hooks —
 * so pages stay server-rendered. Centralizing them here means a single place to
 * restyle the whole platform (the intended target for the visual-polish pass).
 */

import Link from "next/link";
import type { ReactNode } from "react";

export function partyTextClass(party: string | null | undefined): string {
  if (!party) return "text-slate-500";
  if (party.startsWith("Republican")) return "text-govred";
  if (party.startsWith("Democrat")) return "text-govblue";
  return "text-slate-500";
}

export function partyDotClass(party: string | null | undefined): string {
  if (!party) return "bg-slate-400";
  if (party.startsWith("Republican")) return "bg-govred";
  if (party.startsWith("Democrat")) return "bg-govblue";
  return "bg-slate-400";
}

export function chamberLabel(chamber: string | null | undefined): string {
  if (chamber === "senate") return "Senate";
  if (chamber === "house") return "House";
  return chamber ?? "";
}

/** Human date from an ISO `YYYY-MM-DD` (parsed as UTC to avoid an off-by-one
 *  from the server's local timezone). Returns "" for null. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** A titled content card. `count` renders a subtle tally next to the title. */
export function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card">
      <h2 className="mb-4 flex items-baseline gap-2 font-display text-lg font-semibold text-govnavy">
        {title}
        {count !== undefined && (
          <span className="text-sm font-normal text-slate-400">{count}</span>
        )}
      </h2>
      {children}
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-sm text-slate-400">{children}</p>;
}

/** A small labelled fact (e.g. "Born · Oct 11, 1950"). */
export function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800">{children}</dd>
    </div>
  );
}

const POSITION_STYLES: Record<string, string> = {
  yea: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  aye: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  nay: "bg-rose-50 text-rose-700 ring-rose-600/20",
  no: "bg-rose-50 text-rose-700 ring-rose-600/20",
  present: "bg-amber-50 text-amber-700 ring-amber-600/20",
};

/** A colored vote-position chip (Yea/Aye green, Nay/No red, Present amber,
 *  everything else neutral). */
export function PositionPill({ position }: { position: string | null | undefined }) {
  const key = (position ?? "").trim().toLowerCase();
  const style = POSITION_STYLES[key] ?? "bg-slate-100 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${style}`}
    >
      {position || "—"}
    </span>
  );
}

/** Small monospace pill for an identifier (bill_id, committee code, etc.). */
export function CodePill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
      {children}
    </span>
  );
}

/** Back-link used at the top of every detail page. */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 text-sm font-medium text-slate-500 transition-colors hover:text-govnavy"
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {children}
    </Link>
  );
}
