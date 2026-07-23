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
    <section className="rounded-xl border border-slate-200/80 bg-white shadow-card">
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
        <h2 className="font-display text-lg font-semibold text-govnavy">{title}</h2>
        {count !== undefined && count > 0 && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            {count}
          </span>
        )}
      </div>
      <div className="p-6">{children}</div>
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-slate-400">{children}</p>;
}

/** A small labelled fact (e.g. "Born · Oct 11, 1950"). */
export function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-1 text-base text-govnavy">{children}</dd>
    </div>
  );
}

const POSITION_STYLES: Record<string, string> = {
  // Yea/Aye: green
  yea: "text-green-800 bg-green-100 ring-green-500/50",
  aye: "text-green-800 bg-green-100 ring-green-500/50",
  // Nay/No: red
  nay: "text-red-800 bg-red-100 ring-red-500/50",
  no: "text-red-800 bg-red-100 ring-red-500/50",
  // Present: amber
  present: "text-amber-800 bg-amber-100 ring-amber-500/50",
  // Not Voting / everything else: neutral
  "not voting": "text-slate-600 bg-slate-100 ring-slate-500/30",
};

/** A colored vote-position chip (Yea/Aye green, Nay/No red, Present amber,
 *  everything else neutral). */
export function PositionPill({ position }: { position: string | null | undefined }) {
  const key = (position ?? "").trim().toLowerCase();
  const style = POSITION_STYLES[key] ?? POSITION_STYLES["not voting"];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ring-inset ${style}`}
    >
      {position || "Not Voting"}
    </span>
  );
}

/** Small monospace pill for an identifier (bill_id, committee code, etc.). */
export function CodePill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-1 font-mono text-xs text-slate-600">
      {children}
    </span>
  );
}

/** Back-link used at the top of every detail page. */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="group inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 transition-colors hover:text-govnavy"
    >
      <svg
        viewBox="0 0 16 16"
        fill="none"
        className="h-4 w-4 transition-transform group-hover:-translate-x-0.5"
        aria-hidden="true"
      >
        <path
          d="M10.75 3.5L5.75 8l5 4.5"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {children}
    </Link>
  );
}
