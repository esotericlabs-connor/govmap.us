import assert from "node:assert/strict";
import { test } from "node:test";

import { formatWeek, labeledIndexes, niceScale, percentOf } from "../lib/chart-scales.mjs";

test("an empty or invalid maximum still gives a 0-1 axis", () => {
  for (const max of [0, -5, Number.NaN, Number.POSITIVE_INFINITY, undefined]) {
    assert.deepEqual(niceScale(/** @type {number} */ (max)), { max: 1, step: 1, ticks: [0, 1] });
  }
});

test("axes round up to whole-number steps", () => {
  assert.deepEqual(niceScale(8), { max: 8, step: 2, ticks: [0, 2, 4, 6, 8] });
  assert.deepEqual(niceScale(41), { max: 60, step: 20, ticks: [0, 20, 40, 60] });
  assert.deepEqual(niceScale(100), { max: 100, step: 50, ticks: [0, 50, 100] });
  assert.deepEqual(niceScale(3), { max: 3, step: 1, ticks: [0, 1, 2, 3] });
  assert.deepEqual(niceScale(1), { max: 1, step: 1, ticks: [0, 1] });
  assert.deepEqual(niceScale(12, 3), { max: 15, step: 5, ticks: [0, 5, 10, 15] });
  assert.deepEqual(niceScale(2.5), { max: 3, step: 1, ticks: [0, 1, 2, 3] });
});

test("every axis covers its maximum within the interval budget", () => {
  for (const maxTicks of [2, 4, 6]) {
    for (let value = 1; value <= 2000; value++) {
      const { max, step, ticks } = niceScale(value, maxTicks);
      assert.ok(max >= value, `${value}: max ${max}`);
      assert.ok(Number.isInteger(step) && step >= 1, `${value}: step ${step}`);
      assert.ok(ticks.length - 1 <= maxTicks, `${value}: ${ticks.length - 1} intervals`);
      assert.equal(ticks[0], 0);
      assert.equal(ticks.at(-1), max);
      ticks.forEach((tick, i) => assert.equal(tick, i * step));
    }
  }
});

test("bar heights are clamped percentages", () => {
  assert.equal(percentOf(5, 10), 50);
  assert.equal(percentOf(0, 10), 0);
  assert.equal(percentOf(15, 10), 100);
  assert.equal(percentOf(-1, 10), 0);
  assert.equal(percentOf(5, 0), 0);
  assert.equal(percentOf(Number.NaN, 10), 0);
});

test("week labels read in UTC", () => {
  assert.equal(formatWeek("2026-10-19"), "Oct 19");
  assert.equal(formatWeek("2026-11-09"), "Nov 9");
  assert.equal(formatWeek("not a date"), "not a date");
});

test("axis labels thin out from the newest point", () => {
  assert.deepEqual([...labeledIndexes(12, 6)].sort((a, b) => a - b), [1, 3, 5, 7, 9, 11]);
  assert.deepEqual([...labeledIndexes(13, 6)].sort((a, b) => a - b), [0, 3, 6, 9, 12]);
  assert.deepEqual([...labeledIndexes(4, 6)].sort((a, b) => a - b), [0, 1, 2, 3]);
  assert.equal(labeledIndexes(0).size, 0);
});
