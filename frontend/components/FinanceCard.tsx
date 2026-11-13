import Link from "next/link";

import { formatDate, Section } from "@/components/DetailKit";
import type { MemberFinance } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { legacyItemizationSplit } from "@/lib/money.mjs";

/**
 * Campaign-finance snapshot for a member's latest FEC cycle: the topline totals,
 * where the money came from, and itemized versus unitemized individual totals.
 * Pure server-safe presentation,
 * reusing the app's card / proportional-bar language. Data-only, sourced to the
 * FEC — no interpretation. Itemized "who gave what, when" lives in the donations
 * ledger (loaded separately).
 */

const CTA_CLASS =
  "group mt-6 inline-flex items-center gap-1.5 rounded-full bg-govnavy px-5 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-px hover:bg-govnavy/90";

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

type SourceKey =
  | "individual_contributions"
  | "pac_contributions"
  | "party_contributions"
  | "transfers"
  | "candidate_contribution"
  | "other_receipts";

const SOURCES: { key: SourceKey; label: string; color: string }[] = [
  { key: "individual_contributions", label: "Individuals", color: "var(--color-govblue)" },
  { key: "pac_contributions", label: "Other committees", color: "#f59e0b" /* amber-500 */ },
  { key: "party_contributions", label: "Party", color: "#8b5cf6" /* violet-500 */ },
  { key: "transfers", label: "Transfers", color: "#14b8a6" /* teal-500 */ },
  { key: "candidate_contribution", label: "Candidate contributions", color: "#64748b" /* slate-500 */ },
  { key: "other_receipts", label: "Other", color: "#94a3b8" /* slate-400 */ },
];

export function FinanceCard({
  finance,
  bioguide,
  compact = false,
  onViewDonations,
}: {
  finance: MemberFinance;
  bioguide?: string;
  compact?: boolean;
  onViewDonations?: () => void;
}) {
  const parts = SOURCES.map((s) => ({
    ...s,
    amount: finance[s.key] ?? 0,
  })).filter((p) => Number.isFinite(p.amount) && p.amount > 0);
  const totalSources = parts.reduce((sum, p) => sum + p.amount, 0);
  const split = legacyItemizationSplit(finance.individual_itemized, finance.individual_unitemized);

  return (
    <Section title="Campaign Finance">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Total Raised" value={formatMoney(finance.receipts, compact)} sub="this cycle" />
        <Tile label="Total Spent" value={formatMoney(finance.disbursements, compact)} sub="this cycle" />
        <Tile label="Cash on Hand" value={formatMoney(finance.cash_on_hand, compact)} sub="latest reported balance" />
        <Tile label="Debts" value={formatMoney(finance.debts, compact)} sub="owed by committee" />
      </div>

      {Number.isFinite(totalSources) && totalSources > 0 && (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-warm-500">
            Reported positive receipt categories
          </p>
          <p className="mt-0.5 text-xs text-slate-warm-400">
            Shares of the positive categories shown, not necessarily total receipts. Loans,
            adjustments and missing categories can differ.
          </p>
          <div
            className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-slate-warm-200"
            role="img"
            aria-label="Shares of the positive receipt categories shown"
          >
            {parts.map((p) => (
              <div
                key={p.label}
                style={{ width: `${(p.amount / totalSources) * 100}%`, background: p.color }}
                title={`${p.label}: ${formatMoney(p.amount)}`}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {parts.map((p) => (
              <div key={p.label} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.color }} />
                <span className="font-medium text-slate-warm-600">{p.label}</span>
                <span className="font-semibold text-govnavy">{formatMoney(p.amount)}</span>
                <span className="text-slate-warm-400">({pct(p.amount, totalSources)}%)</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {split && (
        <div className="mt-6 rounded-lg border border-slate-warm-200 bg-slate-warm-50/70 p-4">
          <div className="flex items-baseline justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-warm-500">
              Itemized vs. unitemized individual receipts
            </p>
            <p className="text-xs text-slate-warm-400">of these two reported amounts</p>
          </div>
          <div
            className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-slate-warm-200"
            role="img"
            aria-label="Unitemized and itemized individual receipt amounts"
          >
            <div
              style={{ width: `${split.unitemizedPercent}%`, background: "var(--color-govblue)" }}
            />
            <div
              className="bg-slate-700"
              style={{ width: `${split.itemizedPercent}%` }}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <span className="text-slate-warm-600">
              <span className="font-semibold text-govnavy">{split.unitemizedPercent}%</span>{" "}
              unitemized · {formatMoney(finance.individual_unitemized)}
            </span>
            <span className="text-slate-warm-600">
              <span className="font-semibold text-govnavy">
                {formatMoney(finance.individual_itemized)}
              </span>{" "}
              itemized · {split.itemizedPercent}%
            </span>
          </div>
        </div>
      )}
      {!split && (
        <p className="mt-6 text-xs leading-relaxed text-slate-warm-500">
          Itemized and unitemized amounts cannot be compared here unless both are reported,
          nonnegative, and have a positive combined value.
        </p>
      )}

      {bioguide &&
        (onViewDonations ? (
          // In the blade: swap to the in-blade ledger instead of navigating away,
          // so the map underneath is never torn down.
          <button type="button" onClick={onViewDonations} className={CTA_CLASS}>
            View cached FEC receipt records
            <span className="transition-transform group-hover:translate-x-0.5">→</span>
          </button>
        ) : (
          <Link href={`/members/${bioguide}/donations`} className={CTA_CLASS}>
            View cached FEC receipt records
            <span className="transition-transform group-hover:translate-x-0.5">→</span>
          </Link>
        ))}

      <p className="mt-6 border-t border-slate-warm-200 pt-4 text-xs leading-relaxed text-slate-warm-400">
        <span className="font-semibold text-slate-warm-500">Raised</span> and{" "}
        <span className="font-semibold text-slate-warm-500">Spent</span> cover the {finance.cycle}{" "}
        two-year cycle; <span className="font-semibold text-slate-warm-500">Cash on Hand</span> is
        the latest reported balance, which can include funds from earlier cycles. Gross amounts may
        also include transfers between authorized committees.
        {finance.coverage_end && ` Figures through ${formatDate(finance.coverage_end)}.`} Source:
        Federal Election Commission.
      </p>
    </Section>
  );
}
