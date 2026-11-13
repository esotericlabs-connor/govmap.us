import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cadenceHours,
  classifyFreshness,
  formatAge,
  SOURCE_CADENCE_HOURS,
  staleAfterHours,
} from "../lib/freshness.mjs";

const NOW = Date.parse("2026-11-12T15:00:00Z");

test("a source is stale after two missed runs, and never within six hours of schedule", () => {
  assert.equal(staleAfterHours(0.5), 6.5);
  assert.equal(staleAfterHours(12), 24);
  assert.equal(staleAfterHours(24), 48);
  assert.equal(staleAfterHours(744), 1488);
});

test("unregistered and prototype names fall back to a daily cadence", () => {
  assert.equal(cadenceHours("votes"), 0.5);
  assert.equal(cadenceHours("committee_meetings"), 12);
  assert.equal(cadenceHours("a_new_source"), 24);
  assert.equal(cadenceHours("constructor"), 24);
  assert.equal(cadenceHours("toString"), 24);
  assert.ok(Object.isFrozen(SOURCE_CADENCE_HOURS));
});

test("a source that never succeeded is reported as such", () => {
  assert.equal(classifyFreshness("votes", null, NOW), "never");
  assert.equal(classifyFreshness("votes", "", NOW), "never");
  assert.equal(classifyFreshness("votes", "not a timestamp", NOW), "never");
});

test("freshness flips exactly at the stale threshold", () => {
  assert.equal(classifyFreshness("votes", "2026-11-12T08:30:00Z", NOW), "fresh");
  assert.equal(classifyFreshness("votes", "2026-11-12T08:29:59Z", NOW), "stale");
  assert.equal(classifyFreshness("congress_legislators", "2026-11-10T15:00:00Z", NOW), "fresh");
  assert.equal(classifyFreshness("congress_legislators", "2026-11-10T14:59:00Z", NOW), "stale");
  assert.equal(classifyFreshness("a_new_source", "2026-11-10T15:00:00Z", NOW), "fresh");
  assert.equal(classifyFreshness("a_new_source", "2026-11-10T14:00:00Z", NOW), "stale");
  assert.equal(classifyFreshness("votes", "2026-11-12T15:05:00Z", NOW), "fresh");
});

test("ages read compactly", () => {
  assert.equal(formatAge("2026-11-12T14:59:30Z", NOW), "just now");
  assert.equal(formatAge("2026-11-12T15:05:00Z", NOW), "just now");
  assert.equal(formatAge("2026-11-12T14:35:00Z", NOW), "25 min ago");
  assert.equal(formatAge("2026-11-12T14:01:00Z", NOW), "59 min ago");
  assert.equal(formatAge("2026-11-12T14:00:00Z", NOW), "1 h ago");
  assert.equal(formatAge("2026-11-10T16:00:00Z", NOW), "47 h ago");
  assert.equal(formatAge("2026-11-10T15:00:00Z", NOW), "2 days ago");
  assert.equal(formatAge("garbage", NOW), "unknown");
});
