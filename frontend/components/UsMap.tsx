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
const MAX_K = 22;

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
  x0: number; // projected bounding box (viewBox coords) — drives zoom-to-fit
  y0: number;
  x1: number;
  y1: number;
  fill: string;
  vacant?: boolean; // a House district (or Senate seat) with no current holder
  hover: { title: string; rows: { name: string; party: Party; sub?: string; vacant?: boolean }[] };
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

// ISO date/timestamp -> "Jul 26, 2026" (or null). Date-only strings are parsed
// as local so a UTC midnight can't shift the label back a day.
function formatDay(iso?: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

const FIT_PAD = 1.35; // extra breathing room around a district/state when fitting

// Keep the map covering the viewport so it can never be dragged into the void.
// For scale k, the {x,y} translate is bounded so the WIDTH×HEIGHT frame still
// spans the viewport (x in [WIDTH(1-k), 0], y in [HEIGHT(1-k), 0]).
function clampXY(z: { k: number; x: number; y: number }): { k: number; x: number; y: number } {
  return {
    k: z.k,
    x: clamp(z.x, WIDTH * (1 - z.k), 0),
    y: clamp(z.y, HEIGHT * (1 - z.k), 0),
  };
}

// Rough continental-US silhouette — the "zoom out to the whole country" glyph.
function UsShapeIcon() {
  return (
    <svg viewBox="0 0 24 14" fill="currentColor" className="h-3.5 w-6" aria-hidden="true">
      <path d="M1 4.5 6 3.5 12 3.2 18 3.5 23 4.4 22 6 19.5 6.6 18.2 8.4 16.6 8.9 16 11.4 14.4 12 13.7 10 12 10.7 10.4 9.2 7.4 9.8 5.4 8.4 3.8 6.3 1 4.5Z" />
    </svg>
  );
}

export function UsMap({ map, result = null }: { map: CongressMap; result?: LookupResult | null }) {
  const { result: homeResult } = useHomeZip();
  const svgRef = useRef<SVGSVGElement>(null);
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [geo, setGeo] = useState<{ districts: any[]; states: any[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState({ k: 1, x: 0, y: 0 });
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom; // latest committed zoom, for rAF tweens to read as their start
  const rafRef = useRef<number | null>(null); // in-flight fly-to animation frame
  const [hover, setHover] = useState<{ shape: Shape; x: number; y: number } | null>(null);
  const [popover, setPopover] = useState<Shape | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const flownHome = useRef<LookupResult | null>(null); // fly to a home area at most once per value

  // Curated context for the open popover's seat (special-election date/source),
  // plus when the roster was last refreshed — both surfaced in the vacant popover.
  const popoverVacancy = popover ? map.vacancies?.[popover.key] : undefined;
  const rosterUpdatedLabel = formatDay(map.roster_updated);

  // Programmatic fly-to eases the SVG viewBox with a rAF tween rather than a CSS
  // transform transition: driving zoom through the viewBox (see the <svg> below)
  // re-renders the vector borders crisply every frame, where a CSS `scale()`
  // rasterizes the group and blurs the lines until the animation settles. Direct
  // manipulation (wheel/drag) cancels any tween and sets the zoom immediately.
  const cancelAnim = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const animateZoomTo = useCallback(
    (target: { k: number; x: number; y: number }, duration = 500) => {
      cancelAnim();
      const start = zoomRef.current;
      const t0 = performance.now();
      const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;
      const step = (now: number) => {
        const t = Math.min(1, (now - t0) / duration);
        const e = easeOutCubic(t);
        setZoom({
          k: start.k + (target.k - start.k) * e,
          x: start.x + (target.x - start.x) * e,
          y: start.y + (target.y - start.y) * e,
        });
        rafRef.current = t < 1 ? requestAnimationFrame(step) : null;
      };
      rafRef.current = requestAnimationFrame(step);
    },
    [cancelAnim],
  );

  // Stop any in-flight fly-to if the component unmounts mid-animation.
  useEffect(() => cancelAnim, [cancelAnim]);

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
        const [[x0, y0], [x1, y1]] = path.bounds(f as any);
        const entry = map.house[key];
        if (entry) matched++;
        const party = partyOf(entry?.party);
        out.push({
          key,
          d,
          cx,
          cy,
          x0,
          y0,
          x1,
          y1,
          fill: entry ? PARTY_FILL[party] : "fill-slate-200",
          vacant: !entry,
          hover: {
            title: key,
            rows: entry
              ? [{ name: entry.last_name, party, sub: "Representative" }]
              : [{ name: "Vacant seat", party: "I", sub: "No current representative", vacant: true }],
          },
          href: entry ? `/members/${entry.bioguide}` : undefined,
        });
      }
      if (out.length && matched === 0) {
        console.warn("UsMap: districts drew but none matched /api/map keys — check GEOID→key mapping");
        // Nothing matched at all is a data-load problem, not 435 real vacancies —
        // don't mislabel the whole map as "vacant".
        for (const s of out) {
          if (s.vacant) {
            s.vacant = false;
            s.hover.rows = [{ name: "No data", party: "I" }];
          }
        }
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
      const [[x0, y0], [x1, y1]] = path.bounds(f as any);
      const seats = map.senate[key] ?? [];
      out.push({
        key,
        d,
        cx,
        cy,
        x0,
        y0,
        x1,
        y1,
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
      cancelAnim(); // direct manipulation should track the cursor, not ease
      setPopover(null);
      const rect = el.getBoundingClientRect();
      const cx = ((e.clientX - rect.left) / rect.width) * WIDTH;
      const cy = ((e.clientY - rect.top) / rect.height) * HEIGHT;
      setZoom((z) => {
        const k = clamp(z.k * (e.deltaY < 0 ? 1.2 : 1 / 1.2), MIN_K, MAX_K);
        const px = (cx - z.x) / z.k;
        const py = (cy - z.y) / z.k;
        return clampXY({ k, x: cx - px * k, y: cy - py * k });
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [geo, cancelAnim]);

  // Ease the {k,x,y} view to *fit* a shape to the viewport, scaling by its
  // bounding box so tiny districts zoom in far and big ones don't — every
  // selection lands as large as it can. Uses the rAF viewBox tween so the fly-in
  // stays crisp. Guards NaN bounds (AK/HI off-projection edges).
  const fitTo = useCallback((s: Shape) => {
    const bw = s.x1 - s.x0;
    const bh = s.y1 - s.y0;
    if (![bw, bh, s.cx, s.cy].every(Number.isFinite) || bw <= 0 || bh <= 0) return;
    const k = clamp(Math.min(WIDTH / (bw * FIT_PAD), HEIGHT / (bh * FIT_PAD)), MIN_K, MAX_K);
    const cx = (s.x0 + s.x1) / 2;
    const cy = (s.y0 + s.y1) / 2;
    animateZoomTo(clampXY({ k, x: WIDTH / 2 - k * cx, y: HEIGHT / 2 - k * cy }));
  }, [animateZoomTo]);

  // Smooth step zoom toward the viewport center (the +/- buttons).
  const zoomBy = useCallback((factor: number) => {
    setPopover(null);
    const z = zoomRef.current;
    const k = clamp(z.k * factor, MIN_K, MAX_K);
    const cx = WIDTH / 2;
    const cy = HEIGHT / 2;
    const px = (cx - z.x) / z.k;
    const py = (cy - z.y) / z.k;
    animateZoomTo(clampXY({ k, x: cx - px * k, y: cy - py * k }));
  }, [animateZoomTo]);

  // Ease all the way back out to the whole country.
  const resetView = useCallback(() => {
    setPopover(null);
    flownHome.current = homeResult; // don't immediately re-fly home after a manual reset
    animateZoomTo({ k: 1, x: 0, y: 0 });
  }, [homeResult, animateZoomTo]);

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
    fitTo(shape);
  }, [homeResult, shapes, chamber, fitTo]);

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
      cancelAnim(); // a pan is direct manipulation — no easing
      setPopover(null);
    }
    drag.current.x = e.clientX;
    drag.current.y = e.clientY;
    setZoom((z) => clampXY({ ...z, x: z.x + dx, y: z.y + dy }));
  }
  function endPan() {
    // Keep `moved` readable through the click that fires right after pointerup.
    setTimeout(() => (drag.current = null), 0);
  }

  function onShapeClick(shape: Shape) {
    if (drag.current?.moved) return; // it was a pan, not a click
    setHover(null);
    setPopover(shape);
    fitTo(shape);
  }

  if (failed) {
    return <CongressCartogram map={map} highlight={bioguideHighlight} />;
  }

  // Pan/zoom drives the SVG viewBox (not a CSS transform on the <g>), so the
  // browser re-rasterizes the vector borders at full resolution every frame —
  // they stay crisp while moving instead of blurring and snapping sharp. Derived
  // from the same {k,x,y} the handlers maintain: a translate(x,y) scale(k) of the
  // WIDTH×HEIGHT frame is the viewBox [-x/k, -y/k, W/k, H/k].
  const viewBox = `${-zoom.x / zoom.k} ${-zoom.y / zoom.k} ${WIDTH / zoom.k} ${HEIGHT / zoom.k}`;

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-warm-50">
      {!geo ? (
        <div className="flex h-full w-full animate-pulse items-center justify-center text-sm text-slate-warm-400">
          Loading map…
        </div>
      ) : (
        <>
          <svg
            ref={svgRef}
            viewBox={viewBox}
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
            <defs>
              {/* Vacant seats: a soft diagonal hatch so an empty district reads
                  as "no current holder / election pending", not a data error. */}
              <pattern
                id="vacant-hatch"
                width={6}
                height={6}
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <rect width={6} height={6} className="fill-slate-100" />
                <line x1={0} y1={0} x2={0} y2={6} className="stroke-slate-300" strokeWidth={2} />
              </pattern>
            </defs>
            <g>
              {shapes.map((s) => {
                const isHi = highlight.has(s.key);
                return (
                  <path
                    key={s.key}
                    d={s.d}
                    className={`${s.vacant ? "" : s.fill} ${s.href ? "cursor-pointer" : ""} stroke-white transition-[fill,opacity] duration-150 hover:opacity-80`}
                    fill={s.vacant ? "url(#vacant-hatch)" : undefined}
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

          {/* HUD — chamber toggle (top-left) */}
          <div className="absolute left-3 top-3 z-20 inline-flex rounded-full border border-slate-warm-200 bg-white/90 p-1 shadow-lg backdrop-blur">
            {(["house", "senate"] as const).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => {
                  setHover(null);
                  setPopover(null);
                  setChamber(c);
                }}
                className={`rounded-full px-4 py-1.5 text-sm font-semibold capitalize transition-colors ${
                  chamber === c ? "bg-govnavy text-white shadow" : "text-slate-warm-600 hover:text-govnavy"
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          {hover && (
            <div
              className="pointer-events-none absolute z-30 rounded-lg bg-govnavy px-3 py-2 text-white shadow-lg"
              style={{ left: hover.x, top: hover.y, transform: "translate(-50%, calc(-100% - 10px))" }}
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-white/60">{hover.shape.hover.title}</p>
              {hover.shape.hover.rows.map((r, i) => (
                <p key={i} className="whitespace-nowrap text-sm font-semibold">
                  {r.name}
                  {r.vacant ? (
                    r.sub && <span className="font-normal text-white/60"> · {r.sub}</span>
                  ) : (
                    <span
                      className={
                        r.party === "D" ? "text-govblue-400" : r.party === "R" ? "text-red-400" : "text-slate-400"
                      }
                    >
                      {" "}· {r.party}
                    </span>
                  )}
                </p>
              ))}
            </div>
          )}

          {/* Click popover — anchored top-center; the clicked shape flies to
              center beneath it. */}
          {popover && (
            <div className="absolute left-1/2 top-20 z-30 w-[min(20rem,calc(100%-1.5rem))] -translate-x-1/2 rounded-xl border border-slate-warm-200 bg-white p-4 shadow-xl">
              <div className="absolute right-2 top-2 flex items-center gap-0.5">
                <button
                  type="button"
                  aria-label="Zoom out to the whole country"
                  title="Show the whole country"
                  onClick={resetView}
                  className="flex h-6 w-8 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-warm-100 hover:text-govnavy"
                >
                  <UsShapeIcon />
                </button>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={() => setPopover(null)}
                  className="flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-warm-100 hover:text-govnavy"
                >
                  ✕
                </button>
              </div>
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
              {popover.vacant ? (
                <div className="mt-3">
                  <p className="text-xs leading-relaxed text-slate-warm-500">
                    This seat is currently vacant.{" "}
                    {popoverVacancy?.special_election_date && formatDay(popoverVacancy.special_election_date) ? (
                      <>
                        A special election is scheduled for{" "}
                        <span className="font-semibold text-govnavy">
                          {formatDay(popoverVacancy.special_election_date)}
                        </span>
                        . GovMap updates automatically once a new representative is seated.
                      </>
                    ) : (
                      <>A special election will fill it — GovMap updates automatically once a new representative is seated.</>
                    )}
                  </p>
                  {popoverVacancy?.note && (
                    <p className="mt-1 text-xs leading-relaxed text-slate-warm-500">{popoverVacancy.note}</p>
                  )}
                  {popoverVacancy?.source_url && (
                    <a
                      href={popoverVacancy.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-govblue transition-colors hover:text-govnavy"
                    >
                      Election details
                      <span aria-hidden="true">↗</span>
                    </a>
                  )}
                  {rosterUpdatedLabel && (
                    <p className="mt-2 text-[11px] text-slate-warm-400">Roster current as of {rosterUpdatedLabel}</p>
                  )}
                </div>
              ) : (
                popover.href && (
                  <Link
                    href={popover.href}
                    className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-govblue transition-colors hover:text-govnavy"
                  >
                    View profile
                    <span aria-hidden="true">→</span>
                  </Link>
                )
              )}
            </div>
          )}

          {/* HUD — zoom controls (bottom-right) */}
          <div className="absolute bottom-3 right-3 z-20 flex flex-col overflow-hidden rounded-lg border border-slate-warm-200 bg-white/95 shadow-lg backdrop-blur">
            <button
              type="button"
              aria-label="Zoom in"
              className="px-2.5 py-1.5 text-lg font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
              onClick={() => zoomBy(1.5)}
            >
              +
            </button>
            <button
              type="button"
              aria-label="Zoom out"
              className="border-t border-slate-warm-200 px-2.5 py-1.5 text-lg font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
              onClick={() => zoomBy(1 / 1.5)}
            >
              −
            </button>
            <button
              type="button"
              aria-label="Reset view"
              className="border-t border-slate-warm-200 px-2.5 py-1.5 text-xs font-semibold text-slate-warm-600 hover:bg-slate-warm-50"
              onClick={resetView}
            >
              Reset
            </button>
          </div>
        </>
      )}
    </div>
  );
}
