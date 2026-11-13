import assert from "node:assert/strict";
import { test } from "node:test";

import {
  defaultMapView,
  MAP_HISTORY_KEY,
  MEMBER_HISTORY_KEY,
  mapViewFromHistory,
  memberEntry,
  memberHref,
  memberLocation,
  parseMapView,
  withMapView,
  withMemberEntry,
  withListHistory,
} from "../lib/workspace-state.ts";

const map = {
  ...defaultMapView(),
  chamber: "senate",
  zoom: { k: 5, x: -1800, y: -900 },
  selectedKey: "WA",
};

test("map snapshots survive serialization without rounding the viewport", () => {
  const saved = { ...map, zoom: { k: 5.123, x: -1800.456, y: -900.789 } };
  assert.deepEqual(parseMapView(JSON.parse(JSON.stringify(saved))), saved);
  assert.deepEqual(mapViewFromHistory(withMapView({}, saved)), saved);
  assert.notEqual(defaultMapView().zoom, defaultMapView().zoom);
});

test("only map view state is accepted, not arbitrary fields or cached records", () => {
  assert.deepEqual(parseMapView({ ...map, response: { member: "old data" }, query: "private" }), map);
  assert.equal(mapViewFromHistory(null), null);
  assert.equal(mapViewFromHistory({ __NA: true }), null);
});

test("tiny floating-point errors at the viewport bounds are clamped", () => {
  const saved = { ...map, zoom: { k: 5, x: -3840.00000001, y: 0.00000001 } };
  assert.deepEqual(parseMapView(saved).zoom, { k: 5, x: -3840, y: 0 });
});

test("incompatible geometry, invalid viewports and invalid selections fail explicitly", () => {
  for (const value of [
    null,
    [],
    {},
    { ...map, version: 0 },
    { ...map, geometry: "districts-120-v1" },
    { ...map, chamber: "executive" },
    { ...map, zoom: { ...map.zoom, k: 0 } },
    { ...map, zoom: { ...map.zoom, k: 23 } },
    { ...map, zoom: { ...map.zoom, x: Infinity } },
    { ...map, zoom: { ...map.zoom, y: NaN } },
    { ...map, zoom: { ...map.zoom, x: 1 } },
    { ...map, zoom: { ...map.zoom, y: -2401 } },
    { ...map, selectedKey: "WA-7" },
    { ...map, chamber: "house", selectedKey: "WA" },
    { ...map, selectedKey: "<script>" },
  ]) {
    assert.throws(() => parseMapView(value), Error);
  }
  assert.throws(() => mapViewFromHistory({ [MAP_HISTORY_KEY]: {} }), Error);
});

test("map and member history updates retain Next metadata and do not mutate old entries", () => {
  const original = {
    __NA: true,
    __PRIVATE_NEXTJS_INTERNALS_TREE: ["original-route"],
    other: "untouched",
  };
  const first = withMapView(original, map);
  const entry = panelEntry("/?member=C001124");
  const second = withMemberEntry(first, entry);
  const third = withMapView(second, defaultMapView());
  assert.deepEqual(original, {
    __NA: true,
    __PRIVATE_NEXTJS_INTERNALS_TREE: ["original-route"],
    other: "untouched",
  });
  assert.equal(third.__NA, true);
  assert.deepEqual(third.__PRIVATE_NEXTJS_INTERNALS_TREE, ["original-route"]);
  assert.equal(third.other, "untouched");
  assert.deepEqual(third[MEMBER_HISTORY_KEY], entry);
  assert.deepEqual(first[MAP_HISTORY_KEY], map);
  assert.deepEqual(withMemberEntry(second, null), first);
});

test("profile, donations and expansion have distinct URLs while retaining the origin query and hash", () => {
  const origin = "/bills?congress=119#activity";
  const profile = { member: "C001124", view: "profile", expanded: false };
  const donations = { ...profile, view: "donations" };
  const full = { ...donations, expanded: true };
  const profileUrl = memberHref(origin, profile);
  const donationsUrl = memberHref(profileUrl, donations);
  const fullUrl = memberHref(donationsUrl, full);
  assert.equal(profileUrl, "/bills?congress=119&member=C001124#activity");
  assert.notEqual(donationsUrl, profileUrl);
  assert.notEqual(fullUrl, donationsUrl);
  assert.deepEqual(memberLocation(new URL(fullUrl, "https://govmap.us").search), full);
  assert.equal(memberHref(fullUrl, null), origin);
  assert.equal(memberHref(fullUrl, profile), profileUrl);
  assert.deepEqual(memberLocation("?member=C001124"), profile);
});

test("local list filtering preserves member Back/close ownership and map snapshots", () => {
  const href = "/map?member=C001124";
  const entry = panelEntry(href);
  const original = withMapView(withMemberEntry({
    __NA: true, _N: true, __PRIVATE_NEXTJS_INTERNALS_TREE: ["original-route"], other: "retained",
  }, entry), map);
  const nextHref = `${href}&sponsored-C001124_q=tax`;
  const next = withListHistory(original, href, nextHref);
  assert.deepEqual(memberEntry(next, nextHref), { ...entry, href: nextHref });
  assert.deepEqual(mapViewFromHistory(next), map);
  assert.equal(next.__NA, undefined);
  assert.equal(next._N, undefined);
  assert.equal(next.other, "retained");
  assert.deepEqual(next.__PRIVATE_NEXTJS_INTERNALS_TREE, ["original-route"]);
  assert.equal(original[MEMBER_HISTORY_KEY].href, href);
  assert.throws(() => withListHistory(original, href, "/bills?member=C001124"), Error);
  assert.throws(() => withListHistory(original, href, "/map?member=A000001"), Error);
  assert.throws(() => withListHistory(original, href, "https://other.example/map?member=C001124"), Error);
  assert.deepEqual(withListHistory({ __NA: true }, "/bills", "/bills?bills_q=tax"), {});
});

test("candidate member blades retain campaign filters, pagination and return context", () => {
  for (const origin of [
    "/money?cycle=2026&state=TX&offset=20#candidate-H2TX30178",
    "/money/H2TX30178?cycle=2026&returnTo=%2Fmoney%3Fstate%3DTX",
    "/elections?cycle=2026&office=H&offset=50",
  ]) {
    const href = memberHref(origin, { member: "A000001", view: "profile", expanded: false });
    assert.equal(memberHref(href, null), origin);
    assert.equal(memberLocation(new URL(href, "https://govmap.invalid").search).member, "A000001");
  }
});

test("malformed deep links fail rather than navigating to an invalid panel", () => {
  assert.equal(memberLocation("?congress=119"), null);
  for (const query of [
    "?member=not-a-bioguide",
    "?member=C001124&memberView=invalid",
    "?member=C001124&memberSize=invalid",
  ]) {
    assert.throws(() => memberLocation(query), Error);
  }
});

test("Back/Forward metadata keeps ownership, depth and scroll after serialization", () => {
  const first = panelEntry("/?member=C001124");
  const second = {
    ...panelEntry("/?member=C001124&memberView=donations"),
    id: "second",
    depth: 2,
    scrollTop: 635.5,
  };
  const states = [first, second].map((entry) => JSON.parse(JSON.stringify(withMemberEntry({}, entry))));
  assert.equal(memberEntry(states[0], first.href).depth, 1);
  assert.equal(memberEntry(states[1], second.href).depth, 2);
  assert.equal(memberEntry(states[1], second.href).scrollTop, 635.5);
  assert.equal(memberEntry(states[1], second.href).view, "donations");
  assert.equal(memberEntry(states[0], first.href).view, "profile");
  assert.equal(memberEntry(states[1], "/members/C001124"), null);
});

test("direct-link depth zero never claims an earlier history entry; malformed ownership fails", () => {
  const direct = { ...panelEntry("/?member=C001124"), depth: 0 };
  assert.equal(memberEntry(withMemberEntry({}, direct), direct.href).depth, 0);
  for (const update of [
    { origin: "//other.example/" },
    { origin: "/\\other.example/" },
    { depth: -1 },
    { depth: 1.5 },
    { scrollTop: -100 },
    { scrollTop: Infinity },
  ]) {
    assert.throws(() => memberEntry(withMemberEntry({}, { ...direct, ...update }), direct.href));
  }
});

function panelEntry(href) {
  return {
    ...memberLocation(new URL(href, "https://govmap.us").search),
    version: 1,
    id: "first",
    href,
    origin: "/",
    depth: 1,
    scrollTop: 0,
  };
}
