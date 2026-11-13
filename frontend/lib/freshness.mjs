/**
 * Whether each source's data is current, judged against how often it is
 * scheduled to refresh. Pure, so the server-rendered dashboard and the unit
 * tests agree on exactly when a source counts as stale.
 */

const HOUR_MS = 3_600_000;

/**
 * Scheduled refresh interval in hours per registered source, mirroring
 * backend/app/scheduler.py. Update both together.
 */
export const SOURCE_CADENCE_HOURS = Object.freeze({
  congress_legislators: 24,
  congress_gov_bills: 0.5,
  votes: 0.5,
  member_sponsored: 24,
  fec_finance: 24,
  fec_candidates: 24,
  fec_election_calendar: 24,
  committee_meetings: 12,
  backfill_bills: 0.5,
  zip_districts: 24 * 31,
});

const DEFAULT_CADENCE_HOURS = 24;

/** @typedef {"fresh" | "stale" | "never"} Freshness */

/**
 * Hours after the last success at which a source is stale: two missed runs,
 * and never sooner than six hours past its schedule, so one slow or skipped
 * run doesn't raise a flag.
 * @param {number} cadenceHours
 * @returns {number}
 */
export function staleAfterHours(cadenceHours) {
  return Math.max(cadenceHours * 2, cadenceHours + 6);
}

/**
 * @param {string} source registered source name
 * @returns {number}
 */
export function cadenceHours(source) {
  return Object.hasOwn(SOURCE_CADENCE_HOURS, source)
    ? SOURCE_CADENCE_HOURS[/** @type {keyof typeof SOURCE_CADENCE_HOURS} */ (source)]
    : DEFAULT_CADENCE_HOURS;
}

/**
 * @param {string} source registered source name
 * @param {string | null} lastSuccess ISO timestamp of the last successful refresh
 * @param {number} nowMs reference time, in epoch milliseconds
 * @returns {Freshness}
 */
export function classifyFreshness(source, lastSuccess, nowMs) {
  const at = lastSuccess ? Date.parse(lastSuccess) : Number.NaN;
  if (Number.isNaN(at)) return "never";
  return nowMs - at > staleAfterHours(cadenceHours(source)) * HOUR_MS ? "stale" : "fresh";
}

/**
 * Plain-language refresh schedule: "Every 30 minutes", "Twice a day", "Daily",
 * "Monthly".
 * @param {string} source registered source name
 * @returns {string}
 */
export function describeCadence(source) {
  const hours = cadenceHours(source);
  if (hours < 1) return `Every ${Math.round(hours * 60)} minutes`;
  if (hours === 12) return "Twice a day";
  if (hours === 24) return "Daily";
  if (hours >= 24 * 28) return "Monthly";
  if (hours % 24 === 0) return `Every ${hours / 24} days`;
  return `Every ${hours} hours`;
}

/**
 * Compact length of time: "45 min", "6.5 h", "2 days".
 * @param {number} hours
 * @returns {string}
 */
export function formatHours(hours) {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 48) return `${Math.round(hours * 10) / 10} h`;
  const days = Math.round(hours / 24);
  return `${days} days`;
}

/**
 * Compact age of a timestamp: "just now", "25 min ago", "3 h ago", "4 days ago".
 * A timestamp slightly in the future (clock skew) reads as "just now".
 * @param {string} iso
 * @param {number} nowMs
 * @returns {string}
 */
export function formatAge(iso, nowMs) {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "unknown";
  const minutes = Math.floor(Math.max(0, nowMs - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return `${days} days ago`;
}
