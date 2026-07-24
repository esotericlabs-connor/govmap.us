"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useRef, type MouseEvent } from "react";

import type { CongressMap } from "@/lib/api";

/**
 * Self-contained seat-chart (hemicycle) of Congress. Every seat is one member,
 * colored by party from /api/map — no external geometry, no map tiles, no
* third-party requests. Toggle House / Senate; hover a seat for who it is;
 * click to open their profile; a ZIP lookup rings "your" seats.
 *
 * The polygon geometry is computed here (concentric arcs, seats distributed
 * proportionally to each arc's length and swept left→right by party), so the
 * whole thing is a pile of <circle>s in one responsive <svg>.
 */

type Seat = { bioguide: string; label: string; name: string; party: string };

type PartyKey = "D" | "R" | "I";

// Party → Tailwind fill/text classes; brand colors come straight from the theme.
const PARTY_COLORS = {
  D: {
    base: "text-govblue",
    dot: "bg-govblue",
    fill: "fill-govblue",
  },
  R: {
    base: "text-govred",
    dot: "bg-govred",
    fill: "fill-govred",
  },
  I: {
    base: "text-slate-500",
    dot: "bg-slate-400",
    fill: "fill-slate-400",
  },
};

function partyKey(party: string): PartyKey {
  if (party.startsWith("Democrat")) return "D";
  if (party.startsWith("Republican")) return "R";
  return "I";
}

// Order seats left→right: Democrats, Independents, Republicans.
const PARTY_ORDER: Record<PartyKey, number> = { D: 0, I: 1, R: 2 };

type Pt = { x: number; y: number; theta: number; r: number };

/** Distribute `n` seats over `rows` concentric semicircles, returned in
 *  left→right (then inner→outer) fill order. Geometry is in arc-radius units
 *  centered on the origin, baseline at y=0, dome above (negative y). */
function hemicycle(n: number, rows: number, innerR: number, outerR: number): Pt[] {
  if (n <= 0) return [];
  const radii: number[] = [];
  for (let i = 0; i < rows; i++) {
    const t = rows === 1 ? 1 : i / (rows - 1);
    radii.push(innerR + (outerR - innerR) * t);
  }
  const totalR = radii.reduce((a, b) => a + b, 0);
  const counts = radii.map((r) => Math.max(1, Math.floor((n * r) / totalR)));

  // Reconcile rounded counts to exactly n (adjust outer rows first).
  let assigned = counts.reduce((a, b) => a + b, 0);
  let i = rows - 1;
  let guard = 0;
  while (assigned > n && guard++ < 10000) {
    if (counts[i] > 1) {
      counts[i]--;
      assigned--;
    }
    i = i === 0 ? rows - 1 : i - 1;
  }
  i = rows - 1;
  while (assigned < n && guard++ < 10000) {
    counts[i]++;
    assigned++;
    i = i === 0 ? rows - 1 : i - 1;
  }

  const pts: Pt[] = [];
  radii.forEach((r, ri) => {
    const c = counts[ri];
    for (let k = 0; k < c; k++) {
      const theta = c === 1 ? Math.PI / 2 : Math.PI - (Math.PI * k) / (c - 1);
      pts.push({ r, theta, x: Math.cos(theta) * r, y: -Math.sin(theta) * r });
    }
  });
  pts.sort((a, b) => b.theta - a.theta || a.r - b.r);
  return pts;
}

const CHART = {
  house: { rows: 12, innerR: 48, outerR: 100, dot: 2.1, stroke: 1.2 },
  senate: { rows: 5, innerR: 52, outerR: 100, dot: 4.5, stroke: 1.5 },
} as const;

const CX = 110;
const CY = 108;

function seatsFor(map: CongressMap, chamber: "house" | "senate"): Seat[] {
  const seats: Seat[] =
    chamber === "house"
      ? Object.entries(map.house).map(([label, e]) => ({
          bioguide: e.bioguide,
          label,
          name: e.last_name,
          party: e.party,
        }))
      : Object.entries(map.senate).flatMap(([state, arr]) =>
          arr.map((e) => ({
            bioguide: e.bioguide,
            label: state,
            name: e.last_name,
            party: e.party,
          })),
        );
  return seats.sort(
    (a, b) =>
      PARTY_ORDER[partyKey(a.party)] - PARTY_ORDER[partyKey(b.party)] ||
      a.label.localeCompare(b.label),
  );
}

function CartogramSkeleton() {
  return (
    <svg viewBox="0 0 220 120" className="mt-4 w-full animate-pulse" role="presentation">
      <defs>
        <radialGradient id="skeleton-gradient">
          <stop offset="0%" stopColor="#f1f0ee" />
          <stop offset="100%" stopColor="#e4e2de" />
        </radialGradient>
      </defs>
      {hemicycle(435, 12, 48, 100).map((p, i) => (
        <circle
          key={i}
          cx={CX + p.x}
          cy={CY + p.y}
          r={CHART.house.dot}
          className="fill-slate-200"
        />
      ))}
    </svg>
  );
}

function Tooltip({ seat, pos }: { seat: Seat | null; pos: { x: number; y: number } }) {
  if (!seat) return null;
  const pKey = partyKey(seat.party);
  return (
    <div
      className="pointer-events-none absolute z-10 animate-slide-down-and-fade rounded-lg bg-govnavy px-3 py-2 text-sm text-white shadow-lg"
      style={{ left: pos.x, top: pos.y, transform: "translate(-50%, -100%)" }}
    >
      <p className="whitespace-nowrap font-bold">{seat.name}</p>
      <p className={`whitespace-nowrap text-sm ${pKey === "D" ? "text-govblue-400" : pKey === "R" ? "text-red-400" : "text-slate-400"}`}>
        {pKey} · {seat.label}
      </p>
    </div>
  );
}

export function CongressCartogram({
  map,
  highlight,
}: {
  map: CongressMap;
  highlight: Set<string>;
}) {
  const router = useRouter();
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [hovered, setHovered] = useState<Seat | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const seats = useMemo(() => seatsFor(map, chamber), [map, chamber]);
  const cfg = CHART[chamber];
  const positions = useMemo(
    () => hemicycle(seats.length, cfg.rows, cfg.innerR, cfg.outerR),
    [seats.length, cfg],
  );

  const hasSeats = seats.length > 0;

  function onSeatEnter(e: MouseEvent, seat: Seat) {
    setHovered(seat);
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      // Position tooltip relative to the container.
      setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top - 20 });
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <Tooltip seat={hovered} pos={hoverPos} />

      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div className="relative isolate inline-flex rounded-full border border-slate-warm-200 bg-slate-warm-50 p-1">
          {(["house", "senate"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => {
                setHovered(null);
                setChamber(c);
              }}
              className={`relative z-10 rounded-full px-4 py-1.5 text-sm font-semibold capitalize transition-colors duration-300 ${
                chamber === c ? "text-white" : "text-slate-warm-600 hover:text-govnavy"
              }`}
            >
              {c}
            </button>
          ))}
          <span
            className="absolute inset-y-1 left-1 z-0 w-[calc(50%-4px)] rounded-full bg-govnavy shadow-md transition-transform duration-300 ease-in-out"
            style={{ transform: `translateX(${chamber === "senate" ? "100%" : "0"})` }}
          />
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${PARTY_COLORS.D.dot}`} /> Democrat
          </span>
          <span className="flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${PARTY_COLORS.I.dot}`} /> Independent
          </span>
          <span className="flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${PARTY_COLORS.R.dot}`} /> Republican
          </span>
        </div>
      </div>

      {hasSeats ? (
        <div className="relative">
          <svg
            key={chamber} // Re-mounts to trigger animation on chamber change
            viewBox="0 0 220 120"
            className="mt-4 w-full animate-subtle-fade-in"
            role="img"
            aria-label={`Seat chart of the ${chamber === "house" ? "House" : "Senate"}`}
          >
            {positions.map((p, idx) => {
              const seat = seats[idx];
              if (!seat) return null;
              const isHi = highlight.has(seat.bioguide);
              const pKey = partyKey(seat.party);
              const isHovered = hovered?.bioguide === seat.bioguide;

              return (
                <g
                  key={seat.bioguide + idx}
                  className="cursor-pointer"
                  onMouseEnter={(e) => onSeatEnter(e, seat)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => router.push(`/members/${seat.bioguide}`)}
                >
                  {isHi && (
                    <circle
                      cx={CX + p.x}
                      cy={CY + p.y}
                      r={cfg.dot}
                      className={`${PARTY_COLORS[pKey].fill} animate-ring pointer-events-none`}
                    />
                  )}
                  <circle
                    cx={CX + p.x}
                    cy={CY + p.y}
                    r={isHovered ? cfg.dot * 1.3 : cfg.dot}
                    className={`${PARTY_COLORS[pKey].fill} transition-all duration-150`}
                    stroke={isHi ? "rgb(7 11 26 / 0.8)" : "none"}
                    strokeWidth={isHi ? cfg.stroke : 0}
                  >
                    <title>{`${seat.name} (${pKey}) · ${seat.label}`}</title>
                  </circle>
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <CartogramSkeleton />
      )}

      <div className="mt-3 flex min-h-[2.5rem] items-center justify-center rounded-lg bg-slate-warm-50 px-4 py-2 text-center text-sm text-slate-warm-400">
        <span>
          {seats.length > 0 ? `${seats.length} seats · Hover for details, click for profile` : "Seat data is loading..."}
        </span>
      </div>
    </div>
  );
}
