import assert from "node:assert/strict";
import { test } from "node:test";

import { hasNormalizedCalendarRange } from "../lib/election-calendar.mjs";

test("calendar ranges are trusted only when the backend explicitly confirms normalization", () => {
  assert.equal(hasNormalizedCalendarRange({}), false);
  assert.equal(hasNormalizedCalendarRange({ end_date_normalized: false }), false);
  assert.equal(hasNormalizedCalendarRange({ end_date_normalized: true }), true);
});
