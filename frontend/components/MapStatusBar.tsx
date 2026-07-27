"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { ChamberBalance, ChamberSummary } from "@/lib/api";

function timeIn(d: Date, tz?: string): string {
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: tz,
    timeZoneName: "short",
  });
}

// Diagonal hatch used for the "Vacant" swatch, mirroring the map's vacant fill.
const HATCH_STYLE = {
  backgroundImage:
    "repeating-linear-gradient(45deg, #cbd5e1 0, #cbd5e1 1px, #f1f5f9 1px, #f1f5f9 3px)",
} as const;

// --- Hemicycle geometry -----------------------------------------------------

// Rows scale with the seat count so the House (~435) and Senate (100) both read
// as a proper filled arc without being too sparse or too dense.
function seatRows(total: number): number {
  return Math.max(3, Math.min(14, Math.round(Math.sqrt(total / 2.4))));
}

// Seat centers for a parliament-style hemicycle, in a normalized space where the
// flat side sits on y=0 and the dome rises to y=-1, x in [-1, 1]. Seats are
// returned ordered left-to-right so callers can color them D → I → R by slicing.
function hemicycleSeats(total: number, rows: number): { x: number; y: number }[] {
  if (total <= 0) return [];
  const r0 = 0.42; // innermost row radius (fraction of the outer radius)
  const radii = Array.from({ length: rows }, (_, i) =>
    rows === 1 ? 1 : r0 + (1 - r0) * (i / (rows - 1)),
  );
  const radSum = radii.reduce((a, b) => a + b, 0);
  // Seats per row ∝ its radius (outer rows are longer, so they hold more).
  const exact = radii.map((r) => (total * r) / radSum);
  const counts = exact.map((v) => Math.floor(v));
  let rem = total - counts.reduce((a, b) => a + b, 0);
  const byFrac = exact
    .map((v, i) => ({ i, f: v - Math.floor(v) }))
    .sort((a, b) => b.f - a.f);
  for (let k = 0; rem > 0; k++, rem--) counts[byFrac[k % rows].i]++;

  const seats: { x: number; y: number; t: number; r: number }[] = [];
  for (let i = 0; i < rows; i++) {
    const n = counts[i];
    for (let j = 0; j < n; j++) {
      const t = n === 1 ? 0.5 : j / (n - 1); // 0 = left, 1 = right
      const a = Math.PI * (1 - t);
      seats.push({ x: radii[i] * Math.cos(a), y: -radii[i] * Math.sin(a), t, r: radii[i] });
    }
  }
  seats.sort((a, b) => a.t - b.t || a.r - b.r);
  return seats.map(({ x, y }) => ({ x, y }));
}

function ChamberDiagram({ D, I, R }: { D: number; I: number; R: number }) {
  const total = D + I + R;
  const rows = seatRows(total);
  const seats = useMemo(() => hemicycleSeats(total, rows), [total, rows]);
  const dotR = Math.max(1.5, 24 / rows);
  const pct = (n: number) => (total ? (n / total) * 100 : 0);

  const colorFor = (idx: number) =>
    idx < D ? "fill-govblue" : idx < D + I ? "fill-slate-400" : "fill-govred";

  return (
    <div>
      <svg
        viewBox="0 0 220 118"
        className="w-full"
        role="img"
        aria-label={`Seating chart: ${D} Democrat, ${R} Republican${I ? `, ${I} Independent` : ""}`}
      >
        {seats.map((s, idx) => (
          <circle key={idx} cx={110 + s.x * 100} cy={112 + s.y * 100} r={dotR} className={colorFor(idx)} />
        ))}
      </svg>
      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-white/10">
        {D > 0 && <div className="bg-govblue" style={{ width: `${pct(D)}%` }} />}
        {I > 0 && <div className="bg-slate-400" style={{ width: `${pct(I)}%` }} />}
        {R > 0 && <div className="bg-govred" style={{ width: `${pct(R)}%` }} />}
      </div>
    </div>
  );
}

// Shared popover/sheet body: title + seating chart + split counts.
function ChamberPanel({ name, data }: { name: string; data: ChamberBalance }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-white">{name}</span>
        <span className="text-[11px] text-white/40">{data.total} seats</span>
      </div>
      <ChamberDiagram D={data.D} I={data.I} R={data.R} />
      <div className="mt-2.5 flex items-center justify-between text-[11px]">
        <span className="text-govblue-400">
          <b className="text-sm">{data.D}</b> Dem
        </span>
        {data.I > 0 && (
          <span className="text-slate-300">
            <b className="text-sm">{data.I}</b> Ind
          </span>
        )}
        <span className="text-red-400">
          <b className="text-sm">{data.R}</b> Rep
        </span>
      </div>
    </div>
  );
}

// The three party/vacant swatches, as a fragment so each caller lays them out.
function LegendItems() {
  return (
    <>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-govblue" />
        Democrat
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-govred" />
        Republican
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm ring-1 ring-inset ring-white/25" style={HATCH_STYLE} />
        Vacant
      </span>
    </>
  );
}

// Desktop-only interactive chamber stat: the label + D·R numbers illuminate in
// their party color on hover, and clicking slides a seating popover up.
function ChamberStat({
  name,
  data,
  open,
  onToggle,
}: {
  name: string;
  data: ChamberBalance;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-label={`${name} party split — show seating chart`}
        className="flex items-center gap-1.5"
      >
        <span className="font-semibold uppercase tracking-wider text-white/45 transition-all duration-150 hover:text-white hover:[text-shadow:0_0_8px_rgba(255,255,255,0.5)]">
          {name}
        </span>
        <span className="font-semibold text-govblue-400 transition-all duration-150 hover:text-govblue-100 hover:[text-shadow:0_0_10px_rgba(88,169,230,0.9)]">
          {data.D}
        </span>
        <span className="text-white/30">·</span>
        <span className="font-semibold text-red-400 transition-all duration-150 hover:text-red-200 hover:[text-shadow:0_0_10px_rgba(221,25,34,0.9)]">
          {data.R}
        </span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-2 w-56 animate-fade-up rounded-xl border border-white/10 bg-govnavy-800/95 p-3 shadow-2xl backdrop-blur">
          <ChamberPanel name={name} data={data} />
        </div>
      )}
    </div>
  );
}

function LegendIcon() {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true" fill="currentColor">
      <circle cx="3" cy="4" r="2" />
      <rect x="7" y="3" width="7" height="2" rx="1" />
      <circle cx="3" cy="12" r="2" />
      <rect x="7" y="11" width="7" height="2" rx="1" />
    </svg>
  );
}

/**
 * Slim status bar pinned to the bottom of the map app: the party legend +
 * House/Senate balance, plus the viewer's local time (from their browser
 * timezone, which tracks their location — no IP lookup needed) and Washington,
 * DC time.
 *
 * Desktop shows the full legend and interactive House/Senate stats — each opens
 * a seating-chart popover, and the numbers illuminate in their party color on
 * hover. Mobile (where the inline legend gets cut off) collapses to a single
 * bottom-left "Legend" button that opens a sheet: the legend plus a drill-in to
 * each chamber's seating chart. The clock is client-only (SSR-safe) and ticks in.
 */
export function MapStatusBar({ summary }: { summary: ChamberSummary | null }) {
  const [now, setNow] = useState<Date | null>(null);
  const [openChamber, setOpenChamber] = useState<null | "House" | "Senate">(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [mobileView, setMobileView] = useState<"menu" | "House" | "Senate">("menu");
  const statsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);

  // Dismiss the desktop popover on outside click / Escape.
  useEffect(() => {
    if (!openChamber) return;
    const onDown = (e: MouseEvent) => {
      if (statsRef.current && !statsRef.current.contains(e.target as Node)) setOpenChamber(null);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenChamber(null);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [openChamber]);

  const openSheet = () => {
    setMobileView("menu");
    setLegendOpen(true);
  };

  const mobileData =
    mobileView === "House" ? summary?.house : mobileView === "Senate" ? summary?.senate : null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 flex h-9 items-center justify-between gap-4 border-t border-white/10 bg-govnavy-800/95 px-4 text-xs text-white/70 backdrop-blur">
      <div ref={statsRef} className="flex min-w-0 items-center gap-4">
        {/* Mobile: a single Legend button (the inline legend gets cut off here). */}
        <button
          type="button"
          onClick={openSheet}
          className="flex items-center gap-1.5 font-medium text-white/70 transition-colors hover:text-white md:hidden"
          aria-haspopup="dialog"
          aria-expanded={legendOpen}
        >
          <LegendIcon />
          Legend
        </button>

        {/* Desktop: full inline legend. */}
        <div className="hidden items-center gap-4 md:flex">
          <LegendItems />
        </div>

        {summary && (
          <div className="hidden items-center gap-4 md:flex">
            <span className="text-white/20">|</span>
            <ChamberStat
              name="House"
              data={summary.house}
              open={openChamber === "House"}
              onToggle={() => setOpenChamber((c) => (c === "House" ? null : "House"))}
            />
            <ChamberStat
              name="Senate"
              data={summary.senate}
              open={openChamber === "Senate"}
              onToggle={() => setOpenChamber((c) => (c === "Senate" ? null : "Senate"))}
            />
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2 tabular-nums text-white/60 sm:gap-3">
        {now && (
          <>
            <span className="hidden sm:inline">Local {timeIn(now)}</span>
            <span className="sm:hidden">{timeIn(now)}</span>
            <span className="text-white/20">|</span>
            <span>Washington {timeIn(now, "America/New_York")}</span>
          </>
        )}
      </div>

      {/* Mobile legend sheet — portaled to <body> so the bar's backdrop-blur
          (a containing block for fixed elements) can't trap it. Always mounted
          so it can slide. */}
      {typeof document !== "undefined" &&
        createPortal(
          <div className="md:hidden">
            <div
              className={`fixed inset-0 z-[45] bg-black/60 transition-opacity duration-300 ${
                legendOpen ? "opacity-100" : "pointer-events-none opacity-0"
              }`}
              onClick={() => setLegendOpen(false)}
              aria-hidden="true"
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-hidden={!legendOpen}
              className={`fixed inset-x-0 bottom-0 z-[46] transform rounded-t-2xl border-t border-white/10 bg-govnavy-800 p-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-sm text-white/80 shadow-2xl transition-transform duration-300 ease-out ${
                legendOpen ? "translate-y-0" : "translate-y-full"
              }`}
            >
              {mobileView === "menu" ? (
                <>
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm font-semibold text-white">Map legend</span>
                    <button
                      type="button"
                      onClick={() => setLegendOpen(false)}
                      aria-label="Close legend"
                      className="text-white/60 transition-colors hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="flex flex-col gap-2.5">
                    <LegendItems />
                  </div>
                  {summary && (
                    <div className="mt-4 border-t border-white/10 pt-3">
                      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-white/40">
                        Chamber split
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        {(["House", "Senate"] as const).map((c) => {
                          const d = c === "House" ? summary.house : summary.senate;
                          return (
                            <button
                              key={c}
                              type="button"
                              onClick={() => setMobileView(c)}
                              className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-left transition-colors hover:bg-white/10"
                            >
                              <span className="font-semibold text-white">{c}</span>
                              <span className="text-xs">
                                <span className="font-semibold text-govblue-400">{d.D}</span>
                                <span className="text-white/30"> · </span>
                                <span className="font-semibold text-red-400">{d.R}</span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="mb-3 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setMobileView("menu")}
                      className="flex items-center gap-1 text-white/70 transition-colors hover:text-white"
                    >
                      <span aria-hidden="true">←</span> Legend
                    </button>
                    <button
                      type="button"
                      onClick={() => setLegendOpen(false)}
                      aria-label="Close legend"
                      className="text-white/60 transition-colors hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                  {mobileData && <ChamberPanel name={mobileView} data={mobileData} />}
                </>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
