/**
 * FEC amounts arrive as decimal strings. Do not pass them through Number:
 * ranking, labels and visualization must agree even beyond its safe integers.
 */

const ZERO = BigInt(0);
const HUNDRED = BigInt(100);

/**
 * @param {string | null} value
 * @returns {bigint | null}
 */
export function moneyCents(value) {
  if (value === null) return null;
  if (typeof value !== "string") throw new TypeError("Invalid money amount");
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) throw new TypeError("Invalid money amount");
  const cents = BigInt(match[2]) * HUNDRED + BigInt((match[3] ?? "").padEnd(2, "0"));
  return match[1] ? -cents : cents;
}

/**
 * @param {string | null} value
 * @returns {string}
 */
export function formatMoneyExact(value) {
  const cents = moneyCents(value);
  if (cents === null) return "Not reported";
  return formatMoneyCents(cents);
}

/**
 * @param {bigint} cents
 * @returns {string}
 */
export function formatMoneyCents(cents) {
  const negative = cents < ZERO;
  const absolute = negative ? -cents : cents;
  const dollars = (absolute / HUNDRED).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const remainder = (absolute % HUNDRED).toString().padStart(2, "0");
  return `${negative ? "-" : ""}$${dollars}.${remainder}`;
}

/**
 * @param {(string | null)[]} values
 * @returns {string | null}
 */
export function maxPositiveMoney(values) {
  let maximum = ZERO;
  let result = null;
  for (const value of values) {
    const cents = moneyCents(value);
    if (cents !== null && cents > maximum) {
      maximum = cents;
      result = value;
    }
  }
  return result;
}

/**
 * Relative bar length, computed in integer cents and rounded down to 0.01%.
 * @param {string | null} value
 * @param {string | null} maximum
 * @returns {number}
 */
export function moneyPercent(value, maximum) {
  const cents = moneyCents(value);
  const max = moneyCents(maximum);
  if (cents === null || max === null || cents <= ZERO || max <= ZERO) return 0;
  const hundredths = (cents * BigInt(10_000)) / max;
  return Math.min(100, Number(hundredths > BigInt(10_000) ? BigInt(10_000) : hundredths) / 100);
}

/**
 * A shared whole-cent value for each of the eight stack levels.
 * @param {string | null} maximum
 * @returns {bigint | null}
 */
export function moneyStackBlockCents(maximum) {
  const max = moneyCents(maximum);
  if (max === null || max <= ZERO) return null;
  return (max + BigInt(7)) / BigInt(8);
}

/**
 * Up to eight levels, rounded up to the shared block value.
 * @param {string | null} value
 * @param {string | null} maximum
 * @returns {number}
 */
export function moneyStackLevels(value, maximum) {
  const cents = moneyCents(value);
  const block = moneyStackBlockCents(maximum);
  if (cents === null || block === null || cents <= ZERO) return 0;
  const levels = (cents + block - BigInt(1)) / block;
  return Number(levels > BigInt(8) ? BigInt(8) : levels);
}

/**
 * Legacy member-finance fields are floating-point amounts, not exact cents.
 * @param {number | null} itemized
 * @param {number | null} unitemized
 * @returns {{itemizedPercent: number, unitemizedPercent: number} | null}
 */
export function legacyItemizationSplit(itemized, unitemized) {
  if (
    typeof itemized !== "number" || !Number.isFinite(itemized) || itemized < 0
    || typeof unitemized !== "number" || !Number.isFinite(unitemized) || unitemized < 0
  ) return null;
  const total = itemized + unitemized;
  if (!Number.isFinite(total) || total <= 0) return null;
  const unitemizedPercent = Math.round((unitemized / total) * 100);
  return { unitemizedPercent, itemizedPercent: 100 - unitemizedPercent };
}
