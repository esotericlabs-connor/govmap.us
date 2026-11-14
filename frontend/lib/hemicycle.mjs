/**
 * Seat geometry for parliament-style hemicycle charts, shared by every seat
 * chart so the House and Senate are always drawn the same way.
 *
 * Coordinates are normalized: the flat side sits on y = 0, the dome rises to
 * y = -1 and x runs from -1 to 1, so callers scale by their outer radius and
 * translate to their center.
 */

/** @typedef {{ x: number, y: number }} Seat */

/**
 * A row count that suits the seat count, so the House (~435) and Senate (100)
 * both read as a filled arc without being too sparse or too dense.
 * @param {number} total
 * @returns {number}
 */
export function seatRows(total) {
  return Math.max(3, Math.min(14, Math.round(Math.sqrt(total / 2.4))));
}

/**
 * Seat centers ordered left to right (then inner to outer), so callers color a
 * chamber D → I → R by slicing. Each row holds seats in proportion to its
 * length; the remainder goes to the rows that lost the most to rounding.
 * @param {number} total seats to place
 * @param {number} rows concentric rows
 * @param {number} [innerRadius] innermost row radius, as a fraction of the outer
 * @returns {Seat[]}
 */
export function hemicycleSeats(total, rows, innerRadius = 0.42) {
  if (!(total > 0) || !(rows >= 1)) return [];
  const count = Math.floor(total);
  const rowCount = Math.floor(rows);
  const radii = Array.from({ length: rowCount }, (_, i) =>
    rowCount === 1 ? 1 : innerRadius + (1 - innerRadius) * (i / (rowCount - 1)),
  );
  const radiusSum = radii.reduce((a, b) => a + b, 0);
  const exact = radii.map((r) => (count * r) / radiusSum);
  const counts = exact.map((v) => Math.floor(v));
  const byRemainder = exact
    .map((v, i) => ({ i, remainder: v - Math.floor(v) }))
    .sort((a, b) => b.remainder - a.remainder);
  let left = count - counts.reduce((a, b) => a + b, 0);
  for (let k = 0; left > 0; k++, left--) counts[byRemainder[k % rowCount].i]++;

  /** @type {{ x: number, y: number, t: number, r: number }[]} */
  const seats = [];
  radii.forEach((r, row) => {
    const n = counts[row];
    for (let j = 0; j < n; j++) {
      const t = n === 1 ? 0.5 : j / (n - 1); // 0 = far left, 1 = far right
      const angle = Math.PI * (1 - t);
      seats.push({ x: r * Math.cos(angle), y: -r * Math.sin(angle), t, r });
    }
  });
  seats.sort((a, b) => a.t - b.t || a.r - b.r);
  return seats.map(({ x, y }) => ({ x, y }));
}
