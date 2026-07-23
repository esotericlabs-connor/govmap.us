import Link from "next/link";

import type { ChamberBalance, ChamberSummary } from "@/lib/api";

/**
 * The House vs Senate split: two distinct panels, each with a party-balance bar
 * and a "browse this chamber" link. Pure server-safe presentation — the page
 * fetches /api/summary and passes it in.
 */

function BalanceBar({ b }: { b: ChamberBalance }) {
  const total = b.total || 1;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div
      className="flex h-3 w-full overflow-hidden rounded-full bg-slate-200"
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
    <span className="flex items-center gap-1.5 text-slate-600">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
      {label} <span className="font-bold text-govnavy">{n}</span>
    </span>
  );
}

function ChamberPanel({
  title,
  subtitle,
  chamber,
  b,
}: {
  title: string;
  subtitle: string;
  chamber: "house" | "senate";
  b: ChamberBalance;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200/80 bg-white p-6 shadow-card">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-xl font-bold text-govnavy">{title}</h3>
        <span className="shrink-0 text-sm text-slate-500">{b.total} seats</span>
      </div>
      <p className="mt-1 text-sm text-slate-500">{subtitle}</p>

      <div className="mt-5">
        <BalanceBar b={b} />
      </div>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <Legend color="bg-govblue" label="Democrat" n={b.D} />
        {b.I > 0 && <Legend color="bg-slate-400" label="Independent" n={b.I} />}
        <Legend color="bg-govred" label="Republican" n={b.R} />
      </div>

      <Link
        href={`/members?chamber=${chamber}`}
        className="group mt-6 inline-flex items-center gap-1.5 self-start rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-govnavy/90"
      >
        Browse the {title}
        <span className="transition-transform group-hover:translate-x-0.5">→</span>
      </Link>
    </div>
  );
}

export function ChamberSplit({ summary }: { summary: ChamberSummary }) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <ChamberPanel
        title="The House"
        subtitle="Each member represents one congressional district (plus non-voting delegates)."
        chamber="house"
        b={summary.house}
      />
      <ChamberPanel
        title="The Senate"
        subtitle="Two members per state, regardless of population."
        chamber="senate"
        b={summary.senate}
      />
    </div>
  );
}
