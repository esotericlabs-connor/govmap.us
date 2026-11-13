import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cadenceHours,
  classifyFreshness,
  describeCadence,
  formatAge,
  formatHours,
  parseFreshnessReferenceTime,
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
  assert.equal(cadenceHours("fec_candidates"), 24);
  assert.equal(cadenceHours("fec_election_calendar"), 24);
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

test("freshness requires a valid API reference timestamp", () => {
  assert.equal(parseFreshnessReferenceTime("2026-11-12T15:00:00Z"), NOW);
  assert.equal(parseFreshnessReferenceTime("2026-11-12T15:00:00+00:00"), NOW);
  assert.equal(parseFreshnessReferenceTime("2026-11-12T10:00:00.000000-05:00"), NOW);
  for (const timestamp of [
    undefined,
    null,
    "",
    "not a timestamp",
    "0",
    "2026-11-12",
    "2026-11-12T15:00:00",
    "2026-02-30T15:00:00Z",
    "2026-11-12T24:00:00Z",
    0,
    {},
  ]) {
    assert.throws(() => parseFreshnessReferenceTime(timestamp), /invalid freshness reference/);
  }
  for (const nowMs of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    assert.throws(
      () => classifyFreshness("votes", "2026-11-12T15:00:00Z", nowMs),
      /Invalid freshness reference/,
    );
  }
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

test("FEC catalog freshness uses the same 48-hour boundary for both sources", () => {
  for (const source of ["fec_candidates", "fec_election_calendar"]) {
    assert.equal(classifyFreshness(source, "2026-11-10T15:00:00Z", NOW), "fresh");
    assert.equal(classifyFreshness(source, "2026-11-10T14:59:59.999Z", NOW), "stale");
    assert.equal(classifyFreshness(source, "2026-11-10T14:59:59Z", NOW), "stale");
    assert.equal(classifyFreshness(source, null, NOW), "never");
  }
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

test("refresh schedules read in plain language", () => {
  assert.equal(describeCadence("votes"), "Every 30 minutes");
  assert.equal(describeCadence("committee_meetings"), "Twice a day");
  assert.equal(describeCadence("congress_legislators"), "Daily");
  assert.equal(describeCadence("fec_candidates"), "Daily");
  assert.equal(describeCadence("fec_election_calendar"), "Daily");
  assert.equal(describeCadence("zip_districts"), "Monthly");
  assert.equal(describeCadence("a_new_source"), "Daily");
  // Every registered source gets a phrase, never a raw number of hours.
  for (const source of Object.keys(SOURCE_CADENCE_HOURS)) {
    assert.match(describeCadence(source), /^(Every \d+ (minutes|hours|days)|Twice a day|Daily|Monthly)$/);
  }
});

test("durations read compactly", () => {
  assert.equal(formatHours(0.75), "45 min");
  assert.equal(formatHours(staleAfterHours(0.5)), "6.5 h");
  assert.equal(formatHours(24), "24 h");
  assert.equal(formatHours(48), "2 days");
  assert.equal(formatHours(staleAfterHours(744)), "62 days");
});
