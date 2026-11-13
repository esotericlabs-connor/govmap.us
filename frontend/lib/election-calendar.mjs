/**
 * @param {{end_date_normalized?: boolean}} event
 * @returns {boolean}
 */
export function hasNormalizedCalendarRange(event) {
  return event.end_date_normalized === true;
}
