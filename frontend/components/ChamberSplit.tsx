import Link from "next/link";

import type { ChamberBalance, ChamberSummary } from "@/lib/api";

/**
 * The House vs Senate split, rendered as a compact status strip beneath the map
 * on /congress: two dense panels, each with a party-balance bar, counts, and a
 * "browse this chamber" link. Pure server-safe presentation — the page fetches
 * /api/summary and passes it in.
 */

function BalanceBar({ b }: { b: ChamberBalance }) {
  const total = b.total || 1;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div
      className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-warm-200"
      role="img"
      aria-label={`${b.D} Democrats, ${b.I} Independents, ${b.R} Republicans`}
    >
      <div className="bg-govblue" style={{ width: pct(b.D) }} />
      <div className="bg-slate-400" style={{ width: pct(b.I) }} />
      <div className="bg-govred" style={{ width: pct(b.R) }} />
    </div>
  );
}

function Legend({ color, label, n }: { color: string; label: string; n: number }) {
  return (
    <div className="flex items-baseline gap-1.5 text-sm">
      <span className={`h-2 w-2 self-center rounded-full ${color}`} />
      <span className="text-slate-warm-500">{label}</span>
      <span className="font-semibold text-govnavy">{n}</span>
    </div>
  );
}

function ChamberPanel({
  title,
  chamber,
  b,
}: {
  title: string;
  chamber: "house" | "senate";
  b: ChamberBalance;
}) {
  return (
    <div className="rounded-2xl border border-slate-warm-200 bg-white p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="font-display text-lg font-bold text-govnavy">{title}</h3>
        <span className="shrink-0 text-xs font-medium text-slate-warm-500">{b.total} seats</span>
      </div>

      <div className="mt-3 space-y-3">
        <BalanceBar b={b} />
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <Legend color="bg-govblue" label="Dem" n={b.D} />
            {b.I > 0 && <Legend color="bg-slate-400" label="Ind" n={b.I} />}
            <Legend color="bg-govred" label="Rep" n={b.R} />
          </div>
          <Link
            href={`/members?chamber=${chamber}`}
            className="group inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govnavy"
          >
            Browse {title}
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </Link>
        </div>
      </div>
    </div>
  );
}

export function ChamberSplit({ summary }: { summary: ChamberSummary }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <ChamberPanel title="The House" chamber="house" b={summary.house} />
      <ChamberPanel title="The Senate" chamber="senate" b={summary.senate} />
    </div>
  );
}
