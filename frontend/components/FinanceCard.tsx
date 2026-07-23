import { formatDate, Section } from "@/components/DetailKit";
import type { MemberFinance } from "@/lib/api";

/**
 * Campaign-finance snapshot for a member's latest FEC cycle: the topline
 * totals + where the receipts came from (individual vs PAC vs party). Pure
 * server-safe presentation, reusing the app's card / proportional-bar language
 * (same as the vote tally bar and the chamber-balance bar). Data-only, sourced
 * to the FEC — no interpretation.
 */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function money(n: number | null | undefined): string {
  return n === null || n === undefined || Number.isNaN(n) ? "—" : USD.format(n);
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200/80 bg-slate-50/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold text-govnavy">{value}</p>
    </div>
  );
}

const SOURCES: { key: keyof MemberFinance; label: string; color: string }[] = [
  { key: "individual_contributions", label: "Individuals", color: "#58A9E6" },
  { key: "pac_contributions", label: "PACs", color: "#F59E0B" },
  { key: "party_contributions", label: "Party", color: "#94A3B8" },
];

export function FinanceCard({ finance }: { finance: MemberFinance }) {
  const parts = SOURCES.map((s) => ({
    ...s,
    amount: (finance[s.key] as number | null) ?? 0,
  })).filter((p) => p.amount > 0);
  const totalContrib = parts.reduce((sum, p) => sum + p.amount, 0);

  return (
    <Section title="Campaign Finance">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Total Raised" value={money(finance.receipts)} />
        <Tile label="Total Spent" value={money(finance.disbursements)} />
        <Tile label="Cash on Hand" value={money(finance.cash_on_hand)} />
        <Tile label="Debts" value={money(finance.debts)} />
      </div>

      {totalContrib > 0 && (
        <div className="mt-6">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
            Where receipts came from
          </p>
          <div className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-slate-200">
            {parts.map((p) => (
              <div
                key={p.label}
                style={{ width: `${(p.amount / totalContrib) * 100}%`, background: p.color }}
                title={`${p.label}: ${money(p.amount)}`}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {parts.map((p) => (
              <span key={p.label} className="flex items-center gap-1.5 text-slate-600">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.color }} />
                {p.label}{" "}
                <span className="font-semibold text-govnavy">{money(p.amount)}</span>
                <span className="text-slate-400">
                  ({Math.round((p.amount / totalContrib) * 100)}%)
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      <p className="mt-6 border-t border-slate-100 pt-4 text-xs text-slate-400">
        {finance.cycle} cycle
        {finance.coverage_end && ` · through ${formatDate(finance.coverage_end)}`} · Source:
        U.S. Federal Election Commission
      </p>
    </Section>
  );
}
