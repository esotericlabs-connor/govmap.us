"use client";

import { useMemo, useState, useRef, type MouseEvent } from "react";

import type { CongressMap } from "@/lib/api";
import { hemicycleSeats } from "@/lib/hemicycle.mjs";
import { useMemberBlade } from "@/lib/member-blade";
import { getPartyKey, PARTY_COLORS, type PartyKey } from "@/lib/party";

/**
 * Self-contained seat-chart (hemicycle) of Congress. Every seat is one member,
 * colored by party from /api/map — no external geometry, no map tiles, no
* third-party requests. Toggle House / Senate; hover a seat for who it is;
 * click to open their profile; a ZIP lookup rings "your" seats.
 *
 * The arc geometry comes from lib/hemicycle.mjs (concentric rows, seats
 * distributed proportionally to each row's length and swept left→right by
 * party), so the whole thing is a pile of <circle>s in one responsive <svg>.
 */

type Seat = { bioguide: string; label: string; name: string; party: string };

// Order seats left→right: Democrats, Independents, Republicans.
const PARTY_ORDER: Record<PartyKey, number> = { D: 0, I: 1, R: 2 };

// Seat rows and the innermost row's radius (as a fraction of OUTER_R).
const CHART = {
  house: { rows: 12, innerRadius: 0.48, dot: 2.1, stroke: 1.2 },
  senate: { rows: 5, innerRadius: 0.52, dot: 4.5, stroke: 1.5 },
} as const;

const OUTER_R = 100;
const CX = 110;
const CY = 108;

/** Seat offsets from (CX, CY) in SVG units, left→right (then inner→outer). */
function seatPositions(n: number, chamber: "house" | "senate"): { x: number; y: number }[] {
  const { rows, innerRadius } = CHART[chamber];
  return hemicycleSeats(n, rows, innerRadius).map(({ x, y }) => ({
    x: x * OUTER_R,
    y: y * OUTER_R,
  }));
}

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
      PARTY_ORDER[getPartyKey(a.party)] - PARTY_ORDER[getPartyKey(b.party)] ||
      a.label.localeCompare(b.label),
  );
}

function CartogramSkeleton() {
  return (
    <svg viewBox="0 0 220 120" className="mt-4 w-full animate-pulse" role="presentation">
      <defs>
        <radialGradient id="skeleton-gradient">
          <stop offset="0%" style={{ stopColor: "rgb(var(--gm-slate-warm-100))" }} />
          <stop offset="100%" style={{ stopColor: "rgb(var(--gm-slate-warm-200))" }} />
        </radialGradient>
      </defs>
      {seatPositions(435, "house").map((p, i) => (
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
  const pKey = getPartyKey(seat.party);
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
  const { open } = useMemberBlade();
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [hovered, setHovered] = useState<Seat | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const seats = useMemo(() => seatsFor(map, chamber), [map, chamber]);
  const cfg = CHART[chamber];
  const positions = useMemo(() => seatPositions(seats.length, chamber), [seats.length, chamber]);

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
              const pKey = getPartyKey(seat.party);
              const isHovered = hovered?.bioguide === seat.bioguide;

              return (
                <g
                  key={seat.bioguide + idx}
                  className="cursor-pointer"
                  onMouseEnter={(e) => onSeatEnter(e, seat)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => open(seat.bioguide)}
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
