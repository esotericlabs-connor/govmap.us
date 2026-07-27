import Link from "next/link";

import { formatDate, Section } from "@/components/DetailKit";
import type { MemberFinance } from "@/lib/api";

/**
 * Campaign-finance snapshot for a member's latest FEC cycle: the topline totals,
 * where the money came from (individual / PAC / party / self / transfers / other),
 * and the small-dollar vs large-dollar split. Pure server-safe presentation,
 * reusing the app's card / proportional-bar language. Data-only, sourced to the
 * FEC — no interpretation. Itemized "who gave what, when" lives in the donations
 * ledger (loaded separately).
 */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

// Abbreviated form ($2.5M / $61.5K / $613) for the narrow blade, where full
// figures overflow the topline tiles.
const USD_COMPACT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

function money(n: number | null | undefined, compact = false): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return (compact ? USD_COMPACT : USD).format(n);
}

function pct(part: number, whole: number): number {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-warm-200 bg-slate-warm-50/70 p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-warm-500">
        {label}
      </p>
      <p className="mt-1 font-display text-2xl font-bold text-govnavy">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-warm-400">{sub}</p>}
    </div>
  );
}

// Receipts by source — these sum to ~total receipts. Self-funding folds in the
// candidate's own contributions and loans; "Other" catches miscellaneous
// receipts. Zero-value sources are dropped so the bar stays clean.
const SOURCES: { key: keyof MemberFinance; label: string; color: string }[] = [
  { key: "individual_contributions", label: "Individuals", color: "var(--color-govblue)" },
  { key: "pac_contributions", label: "PACs", color: "#f59e0b" /* amber-500 */ },
  { key: "party_contributions", label: "Party", color: "#8b5cf6" /* violet-500 */ },
  { key: "transfers", label: "Transfers", color: "#14b8a6" /* teal-500 */ },
  { key: "candidate_contribution", label: "Self-funding", color: "#64748b" /* slate-500 */ },
  { key: "other_receipts", label: "Other", color: "#94a3b8" /* slate-400 */ },
];

export function FinanceCard({
  finance,
  bioguide,
  compact = false,
}: {
  finance: MemberFinance;
  bioguide?: string;
  compact?: boolean;
}) {
  const parts = SOURCES.map((s) => ({
    ...s,
    amount: (finance[s.key] as number | null) ?? 0,
  })).filter((p) => p.amount > 0);
  const totalSources = parts.reduce((sum, p) => sum + p.amount, 0);

  // Grassroots (small-dollar, < $200) share of individual money, when itemized
  // and unitemized are both known.
  const individual = finance.individual_contributions ?? 0;
  const smallDollar = finance.individual_unitemized ?? 0;
  const showSmallDollar = individual > 0 && (finance.individual_unitemized ?? null) !== null;

  return (
    <Section title="Campaign Finance">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Total Raised" value={money(finance.receipts, compact)} sub="this cycle" />
        <Tile label="Total Spent" value={money(finance.disbursements, compact)} sub="this cycle" />
        <Tile label="Cash on Hand" value={money(finance.cash_on_hand, compact)} sub="current balance" />
        <Tile label="Debts" value={money(finance.debts, compact)} sub="owed by committee" />
      </div>

      {totalSources > 0 && (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-warm-500">
            Where the money came from
          </p>
          <p className="mt-0.5 text-xs text-slate-warm-400">
            Share of this cycle&rsquo;s receipts, by source
          </p>
          <div
            className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-slate-warm-200"
            role="img"
            aria-label="Receipts by source"
          >
            {parts.map((p) => (
              <div
                key={p.label}
                style={{ width: `${(p.amount / totalSources) * 100}%`, background: p.color }}
                title={`${p.label}: ${money(p.amount)}`}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {parts.map((p) => (
              <div key={p.label} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.color }} />
                <span className="font-medium text-slate-warm-600">{p.label}</span>
                <span className="font-semibold text-govnavy">{money(p.amount)}</span>
                <span className="text-slate-warm-400">({pct(p.amount, totalSources)}%)</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {showSmallDollar && (
        <div className="mt-6 rounded-lg border border-slate-warm-200 bg-slate-warm-50/70 p-4">
          <div className="flex items-baseline justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-warm-500">
              Grassroots vs. large donors
            </p>
            <p className="text-xs text-slate-warm-400">of individual money</p>
          </div>
          <div
            className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-slate-warm-200"
            role="img"
            aria-label="Small-dollar vs large-dollar individual contributions"
          >
            <div
              style={{ width: `${pct(smallDollar, individual)}%`, background: "var(--color-govblue)" }}
            />
            <div style={{ width: `${100 - pct(smallDollar, individual)}%`, background: "#334155" }} />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <span className="text-slate-warm-600">
              <span className="font-semibold text-govnavy">{pct(smallDollar, individual)}%</span>{" "}
              small-dollar (&lt;&nbsp;$200) · {money(smallDollar)}
            </span>
            <span className="text-slate-warm-600">
              <span className="font-semibold text-govnavy">
                {money(finance.individual_itemized)}
              </span>{" "}
              itemized (larger, disclosed donors)
            </span>
          </div>
        </div>
      )}

      {bioguide && (
        <Link
          href={`/members/${bioguide}/donations`}
          className="group mt-6 inline-flex items-center gap-1.5 rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-px hover:bg-govnavy/90"
        >
          See who gave — itemized donations
          <span className="transition-transform group-hover:translate-x-0.5">→</span>
        </Link>
      )}

      <p className="mt-6 border-t border-slate-warm-200 pt-4 text-xs leading-relaxed text-slate-warm-400">
        <span className="font-semibold text-slate-warm-500">Raised</span> and{" "}
        <span className="font-semibold text-slate-warm-500">Spent</span> cover the {finance.cycle}{" "}
        two-year cycle; <span className="font-semibold text-slate-warm-500">Cash on Hand</span> is
        the committee&rsquo;s running balance, which carries over from earlier cycles — so a member
        can spend more than they raised this cycle by drawing it down.
        {finance.coverage_end && ` Figures through ${formatDate(finance.coverage_end)}.`} Source:
        Federal Election Commission.
      </p>
    </Section>
  );
}
