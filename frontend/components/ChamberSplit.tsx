import Link from "next/link";

import type { ChamberBalance, ChamberSummary } from "@/lib/api";
import { Reveal } from "./Reveal";

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
    <div className="flex items-baseline gap-2 text-sm">
      <div className="flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span className="text-slate-warm-500">{label}</span>
      </div>
      <span className="font-semibold text-govnavy">{n}</span>
    </div>
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
    <div className="flex h-full flex-col rounded-2xl border border-slate-warm-200 bg-white p-6 shadow-card transition-shadow duration-300 hover:shadow-card-hover">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-2xl font-bold text-govnavy">{title}</h3>
        <span className="shrink-0 text-sm font-medium text-slate-warm-500">{b.total} seats</span>
      </div>
      <p className="mt-1 text-sm text-slate-warm-600">{subtitle}</p>

      <div className="mt-auto pt-6">
        <div className="space-y-3">
          <BalanceBar b={b} />
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <Legend color="bg-govblue" label="Democrat" n={b.D} />
            {b.I > 0 && <Legend color="bg-slate-400" label="Independent" n={b.I} />}
            <Legend color="bg-govred" label="Republican" n={b.R} />
          </div>
        </div>

        <Link
          href={`/members?chamber=${chamber}`}
          className="group mt-6 inline-flex items-center gap-1.5 self-start rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-px hover:bg-govnavy/90"
        >
          Browse the {title}
          <span className="transition-transform group-hover:translate-x-0.5">→</span>
        </Link>
      </div>
    </div>
  );
}

export function ChamberSplit({ summary }: { summary: ChamberSummary }) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <Reveal>
        <ChamberPanel
          title="The House"
          subtitle="435 members representing congressional districts, plus non-voting delegates."
          chamber="house"
          b={summary.house}
        />
      </Reveal>
      <Reveal delay={100}>
        <ChamberPanel
          title="The Senate"
          subtitle="100 members, two from each state, regardless of population."
          chamber="senate"
          b={summary.senate}
        />
      </Reveal>
    </div>
  );
}
