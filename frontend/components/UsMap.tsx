"use client";

import { geoAlbersUsa, geoPath } from "d3-geo";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { feature } from "topojson-client";

import { CongressCartogram } from "@/components/CongressCartogram";
import type { CongressMap, LookupResult } from "@/lib/api";
import { useHomeZip } from "@/lib/zip-context";

/**
 * Interactive geographic map of Congress. House view draws one path per
 * congressional district (colored by the representative's party); Senate view
 * draws states (colored by their two seats — split states in violet). Geometry
 * is bundled TopoJSON under /public/geo (see docs/geodata.md) — no map tiles, no
 * third-party requests. Wheel to zoom toward the cursor, drag to pan; hover for
 * who holds the seat, click to open a popover (reps + profile link) that flies
 * the view to that shape. The saved home ZIP rings + flies to your district. If
 * the geometry isn't present yet, it falls back to the
 * self-contained seat chart, so the page always renders something useful.
 */

const WIDTH = 960;
const HEIGHT = 600;
const MIN_K = 1;
const MAX_K = 14;

// 2-digit state/territory FIPS -> USPS (mirrors the backend crosswalk map).
const FIPS_TO_USPS: Record<string, string> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
  "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
  "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
  "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
  "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
  "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
  "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
  "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
  "54": "WV", "55": "WI", "56": "WY", "72": "PR",
};

type Party = "D" | "R" | "I";

function partyOf(p?: string | null): Party {
  if (!p) return "I";
  if (p.startsWith("Democrat")) return "D";
  if (p.startsWith("Republican")) return "R";
  return "I";
}

const PARTY_FILL: Record<Party, string> = {
  D: "fill-govblue",
  R: "fill-govred",
  I: "fill-slate-400",
};

type Shape = {
  key: string; // "WA-7" (house) or "WA" (senate)
  d: string;
  cx: number; // projected centroid (viewBox coords) — anchors zoom + popover
  cy: number;
  fill: string;
  hover: { title: string; rows: { name: string; party: Party; sub?: string }[] };
  href?: string;
};

// GEOID "5307" -> "WA-7"; at-large "5600" -> "WY-0".
function districtKey(rawId: string): string | null {
  const id = rawId.padStart(4, "0");
  const state = FIPS_TO_USPS[id.slice(0, 2)];
  if (!state) return null;
  const district = parseInt(id.slice(2, 4), 10);
  if (Number.isNaN(district)) return null;
  return `${state}-${district}`;
}

function stateKey(rawId: string): string | null {
  return FIPS_TO_USPS[rawId.padStart(2, "0")] ?? null;
}

function senateFill(seats: { party: string }[]): string {
  const parties = seats.map((s) => partyOf(s.party));
  const hasD = parties.includes("D");
  const hasR = parties.includes("R");
  if (hasD && hasR) return "fill-violet-500";
  if (hasR) return "fill-govred";
  if (hasD) return "fill-govblue";
  return "fill-slate-400";
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

export function UsMap({ map, result = null }: { map: CongressMap; result?: LookupResult | null }) {
  const { result: homeResult } = useHomeZip();
  const svgRef = useRef<SVGSVGElement>(null);
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [geo, setGeo] = useState<{ districts: any[]; states: any[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState({ k: 1, x: 0, y: 0 });
  const [animate, setAnimate] = useState(false); // ease the transform only for programmatic fly-to
  const [hover, setHover] = useState<{ shape: Shape; x: number; y: number } | null>(null);
  const [popover, setPopover] = useState<Shape | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const flownHome = useRef<LookupResult | null>(null); // fly to a home area at most once per value

  // Load bundled geometry once. Fall back to the seat chart if it isn't there.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [dTopo, sTopo] = await Promise.all([
          fetch("/geo/districts-119.topo.json").then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
          fetch("/geo/states-119.topo.json").then((r) => (r.ok ? r.json() : Promise.reject(r.status))),
        ]);
        const districts = (feature(dTopo, dTopo.objects.districts) as any).features as any[];
        const states = (feature(sTopo, sTopo.objects.states) as any).features as any[];
        if (alive) setGeo({ districts, states });
      } catch (err) {
        console.warn("UsMap: geometry unavailable, falling back to seat chart:", err);
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const path = useMemo(() => geoPath(geoAlbersUsa()), []);

  const highlight = useMemo(() => {
    const set = new Set<string>();
    for (const r of [result, homeResult]) {
      if (!r) continue;
      for (const d of r.districts) {
        set.add(chamber === "house" ? `${d.state}-${d.district}` : d.state);
      }
    }
    return set;
  }, [result, homeResult, chamber]);

  const bioguideHighlight = useMemo(() => {
    const s = new Set<string>();
    for (const r of [result, homeResult]) {
      if (!r) continue;
      for (const m of [...r.senators, ...r.representatives]) s.add(m.bioguide_id);
    }
    return s;
  }, [result, homeResult]);

  const shapes = useMemo<Shape[]>(() => {
    if (!geo) return [];
    if (chamber === "house") {
      const out: Shape[] = [];
      let matched = 0;
      for (const f of geo.districts) {
        // Works whether mapshaper promoted GEOID to the feature id or left it a
        // property — Census cartographic files always carry GEOID.
        const key = districtKey(String(f.id ?? f.properties?.GEOID ?? ""));
        const d = path(f as any);
        if (!key || !d) continue;
        const [cx, cy] = path.centroid(f as any);
        const entry = map.house[key];
        if (entry) matched++;
        const party = partyOf(entry?.party);
        out.push({
          key,
          d,
          cx,
          cy,
          fill: entry ? PARTY_FILL[party] : "fill-slate-200",
          hover: {
            title: key,
            rows: entry
              ? [{ name: entry.last_name, party, sub: "Representative" }]
              : [{ name: "Vacant / no data", party: "I" }],
          },
          href: entry ? `/members/${entry.bioguide}` : undefined,
        });
      }
      if (out.length && matched === 0) {
        console.warn("UsMap: districts drew but none matched /api/map keys — check GEOID→key mapping");
      }
      return out;
    }
    // Senate: states colored by their two seats.
    const out: Shape[] = [];
    for (const f of geo.states) {
      const key = stateKey(String(f.id ?? f.properties?.STATEFP ?? f.properties?.GEOID ?? ""));
      const d = path(f as any);
      if (!key || !d) continue;
      const [cx, cy] = path.centroid(f as any);
      const seats = map.senate[key] ?? [];
      out.push({
        key,
        d,
        cx,
        cy,
        fill: seats.length ? senateFill(seats) : "fill-slate-200",
        hover: {
          title: key,
          rows: seats.length
            ? seats.map((s) => ({ name: s.last_name, party: partyOf(s.party), sub: "Senator" }))
            : [{ name: "No data", party: "I" }],
        },
        href: seats.length ? `/members/${seats[0].bioguide}` : undefined,
      });
    }
    return out;
  }, [geo, chamber, map, path]);

  // Wheel zoom toward the cursor (native, non-passive so we can preventDefault).
  // Depends on `geo` so it (re)attaches once the <svg> actually mounts.
  useEffect(() => {
    const el = svgRef.current;
    if (!geo || !el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setAnimate(false); // direct manipulation should track the cursor, not ease
      setPopover(null);
      const rect = el.getBoundingClientRect();
      const cx = ((e.clientX - rect.left) / rect.width) * WIDTH;
      const cy = ((e.clientY - rect.top) / rect.height) * HEIGHT;
      setZoom((z) => {
        const k = clamp(z.k * (e.deltaY < 0 ? 1.2 : 1 / 1.2), MIN_K, MAX_K);
        const px = (cx - z.x) / z.k;
        const py = (cy - z.y) / z.k;
        return { k, x: cx - px * k, y: cy - py * k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [geo]);

  // Ease the {k,x,y} transform to center a shape's centroid in the viewport.
  // Only used for programmatic moves (click, fly-to-home) — `animate` gates the
  // CSS transition so drag/wheel stay instant. Guards NaN centroids (AK/HI edges).
  const flyTo = useCallback((cx: number, cy: number, k: number) => {
    if (!Number.isFinite(cx) || !Number.isFinite(cy)) return;
    setAnimate(true);
    setZoom({ k, x: WIDTH / 2 - k * cx, y: HEIGHT / 2 - k * cy });
    window.setTimeout(() => setAnimate(false), 550);
  }, []);

  // When a home area is set (or hydrated from storage), fly to that district/
  // state once. The ref keys off the result value so toggling chambers or
  // re-panning doesn't yank the view back.
  useEffect(() => {
    if (!homeResult || shapes.length === 0) return;
    if (flownHome.current === homeResult) return;
    const d0 = homeResult.districts[0];
    if (!d0) return;
    const key = chamber === "house" ? `${d0.state}-${d0.district}` : d0.state;
    const shape = shapes.find((s) => s.key === key);
    if (!shape) return;
    flownHome.current = homeResult;
    flyTo(shape.cx, shape.cy, chamber === "house" ? 5 : 3);
  }, [homeResult, shapes, chamber, flyTo]);

  function onPointerDown(e: ReactPointerEvent<SVGSVGElement>) {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  }
  function onPointerMove(e: ReactPointerEvent<SVGSVGElement>) {
    if (!drag.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((e.clientX - drag.current.x) / rect.width) * WIDTH;
    const dy = ((e.clientY - drag.current.y) / rect.height) * HEIGHT;
    if (Math.abs(e.clientX - drag.current.x) + Math.abs(e.clientY - drag.current.y) > 3) {
      drag.current.moved = true;
      setAnimate(false); // a pan is direct manipulation — no easing
      setPopover(null);
    }
    drag.current.x = e.clientX;
    drag.current.y = e.clientY;
    setZoom((z) => ({ ...z, x: z.x + dx, y: z.y + dy }));
  }
  function endPan() {
    // Keep `moved` readable through the click that fires right after pointerup.
    setTimeout(() => (drag.current = null), 0);
  }

  function onShapeClick(shape: Shape) {
    if (drag.current?.moved) return; // it was a pan, not a click
    setHover(null);
    setPopover(shape);
    flyTo(shape.cx, shape.cy, chamber === "house" ? 5 : 3);
  }

  if (failed) {
    return <CongressCartogram map={map} highlight={bioguideHighlight} />;
  }

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center justify-between gap-y-3">
        <div className="relative inline-flex rounded-full border border-slate-warm-200 bg-slate-warm-50 p-1">
          {(["house", "senate"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => {
                setHover(null);
                setPopover(null);
                setChamber(c);
              }}
              className={`relative z-10 rounded-full px-4 py-1.5 text-sm font-semibold capitalize transition-colors ${
                chamber === c ? "bg-govnavy text-white shadow" : "text-slate-warm-600 hover:text-govnavy"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-govblue" /> Democrat</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-govred" /> Republican</span>
          {chamber === "senate" && (
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-violet-500" /> Split</span>
          )}
        </div>
      </div>

      <div className="relative mt-4 h-[55vh] min-h-[340px] overflow-hidden rounded-xl border border-slate-warm-200 bg-slate-warm-50 sm:h-[560px]">
        {!geo ? (
          <div className="flex h-full w-full animate-pulse items-center justify-center text-sm text-slate-warm-400">
            Loading map…
          </div>
        ) : (
          <>
            <svg
              ref={svgRef}
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              preserveAspectRatio="xMidYMid meet"
              className="h-full w-full cursor-grab touch-none select-none active:cursor-grabbing"
              role="img"
              aria-label={`Geographic map of the U.S. ${chamber === "house" ? "House by district" : "Senate by state"}`}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={endPan}
              onPointerLeave={() => {
                endPan();
                setHover(null);
              }}
            >
              <g
                className={animate ? "transition-transform duration-500 ease-out" : ""}
                style={{ transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.k})`, transformOrigin: "0 0" }}
              >
                {shapes.map((s) => {
                  const isHi = highlight.has(s.key);
                  return (
                    <path
                      key={s.key}
                      d={s.d}
                      className={`${s.fill} ${s.href ? "cursor-pointer" : ""} stroke-white transition-[fill,opacity] duration-150 hover:opacity-80`}
                      strokeWidth={isHi ? 1.6 : 0.3}
                      stroke={isHi ? "#0b1220" : "#ffffff"}
                      vectorEffect="non-scaling-stroke"
                      onMouseEnter={(e) => {
                        const rect = svgRef.current?.getBoundingClientRect();
                        if (rect) setHover({ shape: s, x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseMove={(e) => {
                        const rect = svgRef.current?.getBoundingClientRect();
                        if (rect) setHover({ shape: s, x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onClick={() => onShapeClick(s)}
                    />
                  );
                })}
              </g>
            </svg>

            {hover && (
              <div
                className="pointer-events-none absolute z-10 rounded-lg bg-govnavy px-3 py-2 text-white shadow-lg"
                style={{ left: hover.x, top: hover.y, transform: "translate(-50%, calc(-100% - 10px))" }}
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-white/60">{hover.shape.hover.title}</p>
                {hover.shape.hover.rows.map((r, i) => (
                  <p key={i} className="whitespace-nowrap text-sm font-semibold">
                    {r.name}
                    <span
                      className={
                        r.party === "D" ? "text-govblue-400" : r.party === "R" ? "text-red-400" : "text-slate-400"
                      }
                    >
                      {" "}· {r.party}
                    </span>
                  </p>
                ))}
              </div>
            )}

            {/* Click popover — anchored to the top of the stage; the clicked
                shape flies to center beneath it. */}
            {popover && (
              <div className="absolute left-1/2 top-3 z-20 w-[min(20rem,calc(100%-1.5rem))] -translate-x-1/2 rounded-xl border border-slate-warm-200 bg-white p-4 shadow-xl">
                <button
                  type="button"
                  aria-label="Close"
                  onClick={() => setPopover(null)}
                  className="absolute right-2.5 top-2.5 flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-warm-100 hover:text-govnavy"
                >
                  ✕
                </button>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-warm-400">
                  {chamber === "house" ? "District" : "State"} {popover.hover.title}
                </p>
                <ul className="mt-2 space-y-1.5">
                  {popover.hover.rows.map((r, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <span
                        className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                          r.party === "D" ? "bg-govblue" : r.party === "R" ? "bg-govred" : "bg-slate-400"
                        }`}
                      />
                      <span className="font-semibold text-govnavy">{r.name}</span>
                      {r.sub && <span className="text-xs text-slate-warm-400">{r.sub}</span>}
                    </li>
                  ))}
                </ul>
                {popover.href && (
                  <Link
                    href={popover.href}
                    className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govnavy"
                  >
                    View profile
                    <span aria-hidden="true">→</span>
                  </Link>
                )}
              </div>
            )}

            {/* Zoom controls */}
            <div className="absolute bottom-3 right-3 flex flex-col overflow-hidden rounded-lg border border-slate-warm-200 bg-white shadow-sm">
              <button
                type="button"
                aria-label="Zoom in"
                className="px-2.5 py-1.5 text-lg font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
                onClick={() => {
                  setAnimate(false);
                  setPopover(null);
                  setZoom((z) => ({ ...z, k: clamp(z.k * 1.3, MIN_K, MAX_K) }));
                }}
              >
                +
              </button>
              <button
                type="button"
                aria-label="Zoom out"
                className="border-t border-slate-warm-200 px-2.5 py-1.5 text-lg font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
                onClick={() => {
                  setAnimate(false);
                  setPopover(null);
                  setZoom((z) => ({ ...z, k: clamp(z.k / 1.3, MIN_K, MAX_K) }));
                }}
              >
                −
              </button>
              <button
                type="button"
                aria-label="Reset view"
                className="border-t border-slate-warm-200 px-2.5 py-1.5 text-xs font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
                onClick={() => {
                  setPopover(null);
                  flownHome.current = homeResult; // don't immediately re-fly home after a manual reset
                  setAnimate(true);
                  setZoom({ k: 1, x: 0, y: 0 });
                  window.setTimeout(() => setAnimate(false), 550);
                }}
              >
                Reset
              </button>
            </div>
          </>
        )}
      </div>

      <p className="mt-3 text-center text-sm text-slate-warm-400">
        {chamber === "house"
          ? "Each district colored by its representative's party · tap a district for its rep · pinch/scroll to zoom, drag to pan"
          : "Each state colored by its two Senate seats · tap a state for its senators · pinch/scroll to zoom, drag to pan"}
      </p>
    </div>
  );
}
