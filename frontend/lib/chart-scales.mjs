/**
 * Axis and label math for the dashboard charts. Kept dependency-free and pure
 * so every chart scales counts the same way and the math is unit-tested.
 */

const NICE_STEPS = [1, 2, 5, 10];

/**
 * A zero-based axis for non-negative whole counts: a round maximum at or
 * above `max`, split into at most `maxTicks` equal whole-number intervals.
 * A missing, zero or invalid maximum gives a 0–1 axis so empty charts still
 * draw a baseline.
 * @param {number} max largest value the axis must show
 * @param {number} [maxTicks] most intervals wanted
 * @returns {{ max: number, step: number, ticks: number[] }}
 */
export function niceScale(max, maxTicks = 4) {
  const top = Number.isFinite(max) && max > 0 ? max : 0;
  if (top === 0) return { max: 1, step: 1, ticks: [0, 1] };
  const intervals = Math.max(1, Math.floor(maxTicks));
  const raw = top / intervals;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const multiple = NICE_STEPS.find((s) => s * magnitude >= raw) ?? 10;
  // Counts are whole numbers, so never step by a fraction.
  const step = Math.max(1, Math.round(multiple * magnitude));
  const niceMax = Math.ceil(top / step) * step;
  const ticks = Array.from({ length: niceMax / step + 1 }, (_, i) => i * step);
  return { max: niceMax, step, ticks };
}

/**
 * `value` as a percentage of `max`, clamped to 0–100, for CSS bar heights.
 * @param {number} value
 * @param {number} max
 * @returns {number}
 */
export function percentOf(value, max) {
  if (!(max > 0) || !Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

const WEEK_FMT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

/**
 * "Oct 19" for an ISO date (YYYY-MM-DD), read in UTC so the server's zone
 * can't shift the label a day. Unparseable input is echoed back.
 * @param {string} iso
 * @returns {string}
 */
export function formatWeek(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : WEEK_FMT.format(d);
}

/**
 * Indexes of the axis labels to print when only about `maxLabels` fit,
 * counted back from the newest so the latest point is always labeled.
 * @param {number} count number of points
 * @param {number} [maxLabels]
 * @returns {Set<number>}
 */
export function labeledIndexes(count, maxLabels = 6) {
  const every = Math.max(1, Math.ceil(count / Math.max(1, maxLabels)));
  const out = new Set();
  for (let i = count - 1; i >= 0; i -= every) out.add(i);
  return out;
}
