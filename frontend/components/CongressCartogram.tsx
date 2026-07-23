"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

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

const FILL: Record<PartyKey, string> = {
  D: "#58A9E6", // govblue
  R: "#DD1922", // govred
  I: "#94a3b8", // slate-400
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
  house: { rows: 12, innerR: 48, outerR: 100, dot: 2.0 },
  senate: { rows: 5, innerR: 52, outerR: 100, dot: 4.2 },
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

  const seats = useMemo(() => seatsFor(map, chamber), [map, chamber]);
  const cfg = CHART[chamber];
  const positions = useMemo(
    () => hemicycle(seats.length, cfg.rows, cfg.innerR, cfg.outerR),
    [seats.length, cfg],
  );

  const hasSeats = seats.length > 0;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1">
          {(["house", "senate"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setChamber(c)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold capitalize transition ${
                chamber === c ? "bg-govnavy text-white shadow-sm" : "text-slate-600 hover:text-govnavy"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: FILL.D }} /> Democrat
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: FILL.I }} /> Independent
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: FILL.R }} /> Republican
          </span>
        </div>
      </div>

      {hasSeats ? (
        <svg
          viewBox="0 0 220 120"
          className="mt-4 w-full"
          role="img"
          aria-label={`Seat chart of the ${chamber === "house" ? "House" : "Senate"}`}
        >
          {positions.map((p, idx) => {
            const seat = seats[idx];
            if (!seat) return null;
            const isHi = highlight.has(seat.bioguide);
            const r = isHi ? cfg.dot * 1.7 : cfg.dot;
            return (
              <circle
                key={seat.bioguide + idx}
                cx={CX + p.x}
                cy={CY + p.y}
                r={r}
                fill={FILL[partyKey(seat.party)]}
                stroke={isHi ? "#070B1A" : "none"}
                strokeWidth={isHi ? 0.9 : 0}
                className="cursor-pointer transition-[r] hover:opacity-80"
                onMouseEnter={() => setHovered(seat)}
                onMouseLeave={() => setHovered((h) => (h === seat ? null : h))}
                onClick={() => router.push(`/members/${seat.bioguide}`)}
              >
                <title>{`${seat.name} (${partyKey(seat.party)}) · ${seat.label}`}</title>
              </circle>
            );
          })}
        </svg>
      ) : (
        <p className="py-16 text-center text-sm text-slate-400">
          Seat data is loading — check back in a moment.
        </p>
      )}

      <div className="mt-3 flex min-h-[2.5rem] items-center justify-center rounded-lg bg-slate-50 px-4 py-2 text-center text-sm">
        {hovered ? (
          <span className="text-slate-700">
            <span className="font-semibold text-govnavy">{hovered.name}</span>{" "}
            ({partyKey(hovered.party)}) · {hovered.label} —{" "}
            <span className="text-govblue">click to open profile</span>
          </span>
        ) : (
          <span className="text-slate-400">
            {seats.length} seats · hover a seat to see who holds it, click to open their profile
          </span>
        )}
      </div>
    </div>
  );
}
