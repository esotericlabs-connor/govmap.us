/**
 * Shared, framework-agnostic formatting helpers (money + dates). Pure functions
 * with no hooks or DOM access, so server and client components can both import
 * them. The three date formatters keep deliberately distinct behaviors (UTC /
 * local / Eastern) — see each one; do not collapse them into a single formatter.
 */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

// Abbreviated form ($2.5M / $61.5K / $613) for narrow layouts (e.g. the member
// blade) where full figures overflow.
const USD_COMPACT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Whole-dollar USD, or an em dash for null/undefined/NaN. `compact` swaps to
 *  the abbreviated form ($2.5M) for space-constrained layouts. */
export function formatMoney(value: number | null | undefined, compact = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (compact ? USD_COMPACT : USD).format(value);
}

/** Human date from an ISO `YYYY-MM-DD`, parsed and rendered in UTC so the
 *  server's local timezone can't shift it a day. Returns "" for null; echoes the
 *  raw input if it can't be parsed. Use for canonical data dates on detail pages. */
export function formatDateUTC(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** ISO date/timestamp -> "Jul 26, 2026" (or null). Date-only strings are parsed
 *  in local time so a UTC midnight can't shift the label back a day. Use for
 *  loosely-typed dates rendered client-side (e.g. map labels). */
export function formatDateLocal(iso?: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

// Committee meetings run on Eastern time; render the UTC timestamp in ET so the
// date/time read as scheduled.
const MEETING_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/New_York",
  timeZoneName: "short",
});

/** ISO timestamp -> "Jul 26, 2026, 10:00 AM EDT" in Eastern time (or null). */
export function formatMeetingTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : MEETING_FMT.format(d);
}
