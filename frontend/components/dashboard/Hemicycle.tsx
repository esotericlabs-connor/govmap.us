/**
 * Party balance of one chamber as a parliament-style seat chart, themed for
 * the dashboard panels. Geometry comes from lib/hemicycle.mjs, the same as the
 * map status bar and the cartogram.
 */

import type { ChamberBalance } from "@/lib/api";
import { hemicycleSeats, seatRows } from "@/lib/hemicycle.mjs";

import { DataState } from "./DataState";

const PARTIES = [
  { key: "D", one: "Democrat", many: "Democrats", dot: "bg-govblue", fill: "fill-govblue" },
  { key: "I", one: "Independent or other", many: "Independents or other", dot: "bg-slate-400", fill: "fill-slate-400" },
  { key: "R", one: "Republican", many: "Republicans", dot: "bg-govred", fill: "fill-govred" },
] as const;

export function Hemicycle({ name, balance }: { name: string; balance: ChamberBalance }) {
  const { D, I, R } = balance;
  const total = D + I + R;
  const shown = PARTIES.filter((p) => p.key !== "I" || I > 0);
  const summary = shown.map((p) => `${balance[p.key]} ${balance[p.key] === 1 ? p.one : p.many}`).join(", ");

  if (total === 0) {
    return (
      <div>
        <h4 className="text-sm font-semibold text-ink">{name}</h4>
        <div className="mt-2">
          <DataState kind="missing">No members of the {name} are loaded yet.</DataState>
        </div>
      </div>
    );
  }

  const rows = seatRows(total);
  const seats = hemicycleSeats(total, rows);
  const dotR = Math.max(1.5, 24 / rows);
  const fillFor = (idx: number) => (idx < D ? PARTIES[0].fill : idx < D + I ? PARTIES[1].fill : PARTIES[2].fill);

  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-ink">{name}</h4>
        <span className="text-xs tabular-nums text-ink-muted">{total.toLocaleString("en-US")} in office</span>
      </div>
      <svg
        viewBox="0 0 220 118"
        className="mt-1 w-full"
        role="img"
        aria-label={`${name} seats held: ${summary}.`}
      >
        {seats.map((s, idx) => (
          <circle key={idx} cx={110 + s.x * 100} cy={112 + s.y * 100} r={dotR} className={fillFor(idx)} />
        ))}
      </svg>
      <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-sunken" aria-hidden="true">
        {shown.map((p) =>
          balance[p.key] > 0 ? (
            <div key={p.key} className={p.dot} style={{ width: `${(balance[p.key] / total) * 100}%` }} />
          ) : null,
        )}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-soft">
        {shown.map((p) => (
          <li key={p.key} className="inline-flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${p.dot}`} aria-hidden="true" />
            <b className="tabular-nums text-ink">{balance[p.key]}</b>
            {balance[p.key] === 1 ? p.one : p.many}
          </li>
        ))}
      </ul>
    </div>
  );
}
