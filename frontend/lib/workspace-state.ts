export const MAP_STORAGE_KEY = "govmap_map_view";
export const MAP_HISTORY_KEY = "govmapMapView";
export const MAP_GEOMETRY = "districts-119-v1";
export const MAP_WIDTH = 960;
export const MAP_HEIGHT = 600;
export const MAP_MIN_ZOOM = 1;
export const MAP_MAX_ZOOM = 22;
const COORDINATE_EPSILON = 0.0000001;

export type MapView = {
  version: 1;
  geometry: typeof MAP_GEOMETRY;
  chamber: "house" | "senate";
  zoom: { k: number; x: number; y: number };
  selectedKey: string | null;
};

export function defaultMapView(): MapView {
  return {
    version: 1,
    geometry: MAP_GEOMETRY,
    chamber: "house",
    zoom: { k: 1, x: 0, y: 0 },
    selectedKey: null,
  };
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseMapView(value: unknown): MapView {
  if (!isRecord(value) || value.version !== 1 || value.geometry !== MAP_GEOMETRY) {
    throw new Error("Saved map view is incompatible with this map version.");
  }
  const { chamber, zoom, selectedKey } = value;
  if (
    (chamber !== "house" && chamber !== "senate") ||
    !isRecord(zoom) ||
    typeof zoom.k !== "number" || !Number.isFinite(zoom.k) || zoom.k < MAP_MIN_ZOOM || zoom.k > MAP_MAX_ZOOM ||
    typeof zoom.x !== "number" || !Number.isFinite(zoom.x) ||
    typeof zoom.y !== "number" || !Number.isFinite(zoom.y) ||
    zoom.x < MAP_WIDTH * (1 - zoom.k) - COORDINATE_EPSILON || zoom.x > COORDINATE_EPSILON ||
    zoom.y < MAP_HEIGHT * (1 - zoom.k) - COORDINATE_EPSILON || zoom.y > COORDINATE_EPSILON ||
    (selectedKey !== null &&
      (typeof selectedKey !== "string" ||
        !(chamber === "house" ? /^[A-Z]{2}-\d{1,2}$/ : /^[A-Z]{2}$/).test(selectedKey)))
  ) {
    throw new Error("Saved map view contains invalid coordinates or selection.");
  }
  return {
    version: 1,
    geometry: MAP_GEOMETRY,
    chamber,
    zoom: {
      k: zoom.k,
      x: Math.min(0, Math.max(MAP_WIDTH * (1 - zoom.k), zoom.x)),
      y: Math.min(0, Math.max(MAP_HEIGHT * (1 - zoom.k), zoom.y)),
    },
    selectedKey,
  };
}

export function mapViewFromHistory(state: unknown): MapView | null {
  if (!isRecord(state) || !(MAP_HISTORY_KEY in state)) return null;
  return parseMapView(state[MAP_HISTORY_KEY]);
}

export function withMapView(state: unknown, view: MapView): Record<string, unknown> {
  return { ...(isRecord(state) ? state : {}), [MAP_HISTORY_KEY]: view };
}

export const MEMBER_HISTORY_KEY = "govmapMember";

export type MemberLocation = {
  member: string;
  view: "profile" | "donations";
  expanded: boolean;
};

export type MemberEntry = MemberLocation & {
  version: 1;
  id: string;
  href: string;
  origin: string;
  depth: number;
  scrollTop: number;
};

export function memberLocation(search: string): MemberLocation | null {
  const params = new URLSearchParams(search);
  const member = params.get("member");
  if (!member) return null;
  if (!/^[A-Z]\d{6}$/.test(member)) throw new Error("Invalid member identifier in link.");
  const view = params.get("memberView");
  const size = params.get("memberSize");
  if ((view !== null && view !== "donations") || (size !== null && size !== "full")) {
    throw new Error("Invalid member view in link.");
  }
  return { member, view: view === "donations" ? "donations" : "profile", expanded: size === "full" };
}

export function memberHref(href: string, location: MemberLocation | null): string {
  const url = new URL(href, "https://govmap.invalid");
  url.searchParams.delete("member");
  url.searchParams.delete("memberView");
  url.searchParams.delete("memberSize");
  if (location) {
    if (!/^[A-Z]\d{6}$/.test(location.member)) throw new Error("Invalid member identifier.");
    url.searchParams.set("member", location.member);
    if (location.view === "donations") url.searchParams.set("memberView", "donations");
    if (location.expanded) url.searchParams.set("memberSize", "full");
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function memberEntry(state: unknown, href: string): MemberEntry | null {
  if (!isRecord(state) || !(MEMBER_HISTORY_KEY in state)) return null;
  const value = state[MEMBER_HISTORY_KEY];
  // An unrelated Next route may inherit metadata, but not our history ownership.
  if (!isRecord(value) || value.href !== href) return null;
  const parsed = memberLocation(new URL(href, "https://govmap.invalid").search);
  if (
    !parsed || value.version !== 1 ||
    typeof value.id !== "string" || value.id.length === 0 || value.id.length > 100 ||
    typeof value.origin !== "string" || !value.origin.startsWith("/") ||
    value.origin.startsWith("//") || value.origin.includes("\\") ||
    typeof value.depth !== "number" || !Number.isSafeInteger(value.depth) || value.depth < 0 ||
    typeof value.scrollTop !== "number" || !Number.isFinite(value.scrollTop) || value.scrollTop < 0
  ) {
    throw new Error("Invalid member navigation history.");
  }
  return {
    ...parsed,
    version: 1,
    id: value.id,
    href,
    origin: value.origin,
    depth: value.depth,
    scrollTop: value.scrollTop,
  };
}

export function withMemberEntry(state: unknown, entry: MemberEntry | null): Record<string, unknown> {
  const next: Record<string, unknown> = { ...(isRecord(state) ? state : {}) };
  if (entry) next[MEMBER_HISTORY_KEY] = entry;
  else delete next[MEMBER_HISTORY_KEY];
  return next;
}
