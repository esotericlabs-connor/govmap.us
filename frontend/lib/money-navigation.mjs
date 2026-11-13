/** @param {unknown} value @returns {value is string} */
function isCandidateId(value) {
  return typeof value === "string" && /^[HSP][A-Z0-9]{8}$/.test(value);
}

/**
 * @param {unknown} candidateId
 * @param {unknown} cycle
 * @returns {boolean}
 */
export function supportsMoneyDetail(candidateId, cycle) {
  return isCandidateId(candidateId)
    && typeof cycle === "number"
    && Number.isSafeInteger(cycle)
    && cycle >= 2000
    && cycle <= 2098
    && cycle % 2 === 0;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function safeMoneyReturn(value) {
  return typeof value === "string"
    && value.length <= 2048
    && !/[\\\r\n]/.test(value)
    && /^\/(?:money|elections)(?:\?[^#]*)?$/.test(value)
    ? value
    : "/money";
}

/**
 * @param {string} candidateId
 * @returns {string}
 */
export function moneyCandidateAnchor(candidateId) {
  if (!isCandidateId(candidateId)) throw new TypeError("Invalid candidate");
  return `candidate-${candidateId}`;
}

/**
 * @param {unknown} value
 * @param {unknown} candidateId
 * @returns {string}
 */
export function moneyReturnHref(value, candidateId) {
  const origin = safeMoneyReturn(value);
  return isCandidateId(candidateId) ? `${origin}#${moneyCandidateAnchor(candidateId)}` : origin;
}

/**
 * @param {string} candidateId
 * @param {number} cycle
 * @param {string} returnTo
 * @returns {string}
 */
export function moneyCandidateHref(candidateId, cycle, returnTo) {
  if (!supportsMoneyDetail(candidateId, cycle)) {
    throw new TypeError("Invalid candidate or finance cycle");
  }
  const query = new URLSearchParams({ cycle: String(cycle), returnTo: safeMoneyReturn(returnTo) });
  return `/money/${encodeURIComponent(candidateId)}?${query.toString()}`;
}
