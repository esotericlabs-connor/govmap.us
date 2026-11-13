import assert from "node:assert/strict";
import { test } from "node:test";

import { hemicycleSeats, seatRows } from "../lib/hemicycle.mjs";

test("row counts grow with the chamber and stay within bounds", () => {
  assert.equal(seatRows(0), 3);
  assert.equal(seatRows(100), 6);
  assert.equal(seatRows(435), 13);
  assert.equal(seatRows(100_000), 14);
});

test("every seat is placed exactly once", () => {
  for (const [total, rows] of [
    [1, 3],
    [2, 3],
    [3, 3],
    [7, 5],
    [100, 5],
    [100, 6],
    [435, 12],
    [441, 13],
  ]) {
    assert.equal(hemicycleSeats(total, rows).length, total, `${total} seats in ${rows} rows`);
  }
});

test("nothing to draw for an empty or invalid chamber", () => {
  assert.deepEqual(hemicycleSeats(0, 5), []);
  assert.deepEqual(hemicycleSeats(-4, 5), []);
  assert.deepEqual(hemicycleSeats(Number.NaN, 5), []);
  assert.deepEqual(hemicycleSeats(10, 0), []);
});

test("seats stay inside the normalized dome", () => {
  for (const { x, y } of hemicycleSeats(435, 12, 0.48)) {
    assert.ok(y <= 1e-9, `y=${y}`);
    assert.ok(Math.abs(x) <= 1 + 1e-9, `x=${x}`);
    const r = Math.hypot(x, y);
    assert.ok(r >= 0.48 - 1e-9 && r <= 1 + 1e-9, `r=${r}`);
  }
});

test("seats run left to right so a party split is a contiguous slice", () => {
  const seats = hemicycleSeats(100, 6);
  const angles = seats.map(({ x, y }) => Math.atan2(-y, x));
  for (let i = 1; i < angles.length; i++) {
    assert.ok(angles[i] <= angles[i - 1] + 1e-9, `seat ${i} is left of seat ${i - 1}`);
  }
  assert.ok(seats[0].x < 0 && seats.at(-1).x > 0);
});

test("outer rows hold more seats than inner rows", () => {
  const seats = hemicycleSeats(435, 12, 0.42);
  const inner = seats.filter(({ x, y }) => Math.abs(Math.hypot(x, y) - 0.42) < 1e-6).length;
  const outer = seats.filter(({ x, y }) => Math.abs(Math.hypot(x, y) - 1) < 1e-6).length;
  assert.ok(inner > 0 && outer > inner, `inner=${inner} outer=${outer}`);
});
