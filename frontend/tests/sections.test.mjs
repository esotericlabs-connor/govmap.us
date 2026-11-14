import assert from "node:assert/strict";
import { test } from "node:test";

import {
  activeSectionId, isWorkspacePath, matchSections, NAVIGATION_GROUPS, normalizeQuery, SECTIONS,
} from "../lib/sections.ts";

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
  assert.deepEqual(ids(matchSections("laws enacted")), ["laws"]);
  assert.deepEqual(ids(matchSections("money campaign")), ids(matchSections("campaign money")));
  assert.deepEqual(matchSections("enacted zzzz"), []);
  assert.deepEqual(matchSections("qqqq"), []);
});

test("the election workspace is findable and links to the live candidate catalog", () => {
  const [elections] = matchSections("midterms");
  assert.equal(elections.id, "elections");
  assert.equal(elections.availability, "live");
  assert.equal(elections.href, "/elections");
  assert.equal(matchSections("judges")[0].id, "judicial");
  assert.equal(matchSections("white house")[0].id, "executive");
});

test("campaign money links to the candidate finance workspace", () => {
  const [money] = matchSections("campaign money");
  assert.equal(money.id, "money");
  assert.equal(money.availability, "live");
  assert.equal(money.href, "/money");
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

test("the data pipeline status page is reachable from search", () => {
  assert.equal(byId("status").href, "/status");
  assert.equal(byId("status").availability, "live");
  assert.equal(matchSections("status")[0].id, "status");
  assert.equal(matchSections("pipeline")[0].id, "status");
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

test("the grouped menu includes each live destination once and separates planned work", () => {
  const groups = NAVIGATION_GROUPS.map((group) => group.id);
  assert.equal(new Set(groups).size, groups.length);
  const live = SECTIONS.filter((section) => section.availability === "live");
  const grouped = NAVIGATION_GROUPS.flatMap((group) =>
    live.filter((section) => section.navigationGroup === group.id),
  );
  assert.deepEqual(ids(grouped).sort(), ids(live).sort());
  for (const section of SECTIONS.filter((section) => section.availability === "planned")) {
    assert.equal(section.navigationGroup, "planned");
    assert.ok(!groups.includes(section.navigationGroup));
  }
});

test("the shared bottom bar covers data workspaces and their nested records", () => {
  for (const pathname of [
    "/", "/map", "/members", "/members/C001124", "/members/C001124/donations",
    "/bills", "/bills/hr1234-119", "/votes", "/votes/h119-2-1",
    "/committees/HSAG", "/elections", "/money", "/money/H2TX30178", "/status",
  ]) {
    assert.equal(isWorkspacePath(pathname), true, pathname);
  }
  for (const pathname of [
    "/about", "/support", "/security", "/privacy", "/account", "/not-found",
    "/money-other", "/membership", "/status-other", "/api/summary",
  ]) {
    assert.equal(isWorkspacePath(pathname), false, pathname);
  }
});

test("active navigation follows detail pages and query-specific destinations", () => {
  const empty = new URLSearchParams();
  assert.equal(activeSectionId("/", empty), "overview");
  assert.equal(activeSectionId("/map", empty), "map");
  assert.equal(activeSectionId("/members/C001124/donations", empty), "members");
  assert.equal(activeSectionId("/money/H2TX30178", empty), "money");
  assert.equal(activeSectionId("/status", empty), "status");
  assert.equal(activeSectionId("/bills", new URLSearchParams("status=became-law")), "laws");
  assert.equal(activeSectionId("/bills", new URLSearchParams("status=introduced")), "bills");
  assert.equal(activeSectionId("/bills/hr1234-119", new URLSearchParams("status=became-law")), "bills");
  assert.equal(activeSectionId("/money-other", empty), null);
});
