import assert from "node:assert/strict";
import { test } from "node:test";

import { matchSections, normalizeQuery, SECTIONS } from "../lib/sections.ts";

const ids = (sections) => sections.map((s) => s.id);
const byId = (id) => SECTIONS.find((s) => s.id === id);

test("an empty query offers the live workspace shortcuts in registry order", () => {
  assert.deepEqual(ids(matchSections("")), ["overview", "map", "members", "bills", "laws"]);
  // The search box shows six, so Votes is reachable without typing.
  assert.deepEqual(ids(matchSections("", 6)), ["overview", "map", "members", "bills", "laws", "votes"]);
  assert.deepEqual(ids(matchSections("   ")), ids(matchSections("")));
  assert.ok(matchSections("").every((s) => s.availability === "live"));
});

test("the overview is home and the map has its own route", () => {
  assert.equal(byId("overview").href, "/");
  assert.equal(byId("map").href, "/map");
  assert.equal(matchSections("home")[0].id, "overview");
  assert.equal(matchSections("dashboard")[0].id, "overview");
  assert.equal(matchSections("map")[0].id, "map");
});

test("queries are case- and whitespace-insensitive", () => {
  assert.equal(normalizeQuery("  Recent   LAWS "), "recent laws");
  assert.deepEqual(ids(matchSections("  BILLS ")), ids(matchSections("bills")));
});

test("label matches outrank keyword matches", () => {
  assert.equal(matchSections("laws")[0].id, "laws");
  assert.equal(matchSections("passed")[0].id, "laws");
  assert.equal(matchSections("votes")[0].id, "votes");
  // "Members" is a label match, "members-elect" only a keyword of Elections.
  assert.equal(matchSections("members")[0].id, "members");
});

test("every query word has to match", () => {
  assert.deepEqual(ids(matchSections("enacted laws")), ["laws"]);
  assert.deepEqual(matchSections("enacted zzzz"), []);
  assert.deepEqual(matchSections("qqqq"), []);
});

test("planned sections are findable and stay labelled as planned", () => {
  const [elections] = matchSections("midterms");
  assert.equal(elections.id, "elections");
  assert.equal(elections.availability, "planned");
  assert.equal(elections.href, "/about#coverage");
  assert.equal(matchSections("judges")[0].id, "judicial");
  assert.equal(matchSections("white house")[0].id, "executive");
});

test("live sections come before planned ones, even on a weaker match", () => {
  const custom = [
    { ...byId("elections"), id: "planned-x", label: "Data", availability: "planned" },
    {
      ...byId("map"),
      id: "live-x",
      label: "Other",
      keywords: ["other"],
      description: "data",
      availability: "live",
    },
  ];
  assert.deepEqual(ids(matchSections("data", 5, custom)), ["live-x", "planned-x"]);
  // "White House" is a label match, but the live House views lead.
  assert.deepEqual(ids(matchSections("house")), ["map", "votes", "executive"]);
});

test("the limit caps the number of shortcuts", () => {
  assert.equal(matchSections("e", 3).length, 3);
});

test("the registry stays internally consistent", () => {
  const seen = new Set();
  for (const s of SECTIONS) {
    assert.ok(!seen.has(s.id), `duplicate section id ${s.id}`);
    seen.add(s.id);
    assert.ok(s.href.startsWith("/") && !s.href.startsWith("//"), `${s.id} must link inside GovMap`);
    assert.ok(s.label && s.description && s.keywords.length > 0, `${s.id} needs search text`);
    if (s.availability === "planned") assert.equal(s.href, "/about#coverage");
  }
});
