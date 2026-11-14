import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { compareListValues, listPageHref, listQuery, localListQuery, matchesListQuery, readListQuery, reconcileListSearch } from "../lib/list-controls.mjs";

test("local search requires every partial word, irrespective of order", () => {
  assert.equal(matchesListQuery("jas crock", "CROCKETT, JASMINE TX"), true);
  assert.equal(matchesListQuery("crock, jas", "CROCKETT, JASMINE TX"), true);
  assert.equal(matchesListQuery("jas unknown", "CROCKETT, JASMINE TX"), false);
  assert.equal(matchesListQuery("%", "Example candidate"), false);
  assert.equal(matchesListQuery("", "Example candidate"), true);
  assert.equal(matchesListQuery("   ", "Example candidate"), true);
  assert.equal(matchesListQuery(",,,", "Example candidate"), false);
});

test("sorting is numeric-aware, stable on ties and always keeps missing values last", () => {
  assert.ok(compareListValues("District 2", "District 10") < 0);
  assert.ok(compareListValues(10, 2, true) < 0);
  assert.ok(compareListValues(null, "Alpha", true) > 0);
  assert.ok(compareListValues("Alpha", null, false) < 0);
  assert.equal(compareListValues(undefined, null, true), 0);
  assert.equal(compareListValues("ALPHA", "alpha"), 0);
  const rows = [{ id: 1, name: "Alpha" }, { id: 2, name: "Alpha" }];
  assert.deepEqual(rows.sort((a, b) => compareListValues(a.name, b.name)).map((row) => row.id), [1, 2]);
});

test("changing criteria clears paging without discarding unrelated workspace state", () => {
  const next = listQuery(
    "offset=100&q=old&sort=name&office=H&member=A000001&calendar_q=primary",
    [["q", " new candidate "], ["sort", "receipts"], ["office", "S"], ["state", ""]],
    ["q", "sort", "office", "state"],
  );
  assert.equal(next.get("q"), "new candidate");
  assert.equal(next.get("sort"), "receipts");
  assert.equal(next.get("office"), "S");
  assert.equal(next.has("offset"), false);
  assert.equal(next.has("state"), false);
  assert.equal(next.get("member"), "A000001");
  assert.equal(next.get("calendar_q"), "primary");
});

test("list URL parsing rejects unsupported sorts and malformed paging", () => {
  assert.deepEqual(readListQuery({}, ["recent", "name"], "recent"), { q: "", sort: "recent", offset: 0, invalid: false });
  for (const params of [{ sort: "arbitrary" }, { offset: "-1" }, { offset: "1.5" }, { offset: "1000001" }, { q: "x".repeat(101) }]) {
    assert.equal(readListQuery(params, ["recent", "name"], "recent").invalid, true);
  }
  assert.equal(readListQuery({ q: [" fair tax ", "ignored"], offset: "50", sort: "name" }, ["recent", "name"], "recent").q, "fair tax");
});

test("FEC paging keeps scroll while each URL retains the selected sort", async () => {
  const component = await readFile(new URL("../components/ListPageLink.tsx", import.meta.url), "utf8");
  assert.match(component, /scroll=\{false\}/);
  for (const path of ["../app/money/page.tsx", "../app/money/[candidateId]/page.tsx", "../app/elections/page.tsx"]) {
    const source = await readFile(new URL(path, import.meta.url), "utf8");
    const pagingLinks = source.match(/<ListPageLink\b[^>]*(?:hrefFor|moneyHref|pageHref)\([^>]*>/g) ?? [];
    assert.ok(pagingLinks.length >= 2, path);
    assert.match(source, /\.set\("sort",/);
  }
});

test("paging preserves independent section controls without restoring the previous page", () => {
  const next = new URL(listPageHref("/elections?offset=50&sort=name", "offset=0&sort=recent&calendar_q=primary&groupings_sort=amount"), "https://govmap.invalid");
  assert.equal(next.searchParams.get("offset"), "50");
  assert.equal(next.searchParams.get("sort"), "name");
  assert.equal(next.searchParams.get("calendar_q"), "primary");
  assert.equal(next.searchParams.get("groupings_sort"), "amount");
});

test("local controls preserve unrelated state and can search the literal word source", () => {
  const searched = localListQuery("office=H&calendar_sort=newest", "calendar", "q", "source");
  assert.equal(searched.get("calendar_q"), "source");
  assert.equal(searched.get("calendar_sort"), "newest");
  assert.equal(searched.get("office"), "H");
  const sorted = localListQuery(searched.toString(), "calendar", "sort", "source");
  assert.equal(sorted.has("calendar_sort"), false);
  assert.equal(sorted.get("calendar_q"), "source");
});

test("own URL acknowledgements preserve newer typing while history navigation restores its query", () => {
  assert.deepEqual(reconcileListSearch({ source: "", draft: "fair tax", submitted: "fair" }, "fair"), {
    source: "fair", draft: "fair tax", submitted: null,
  });
  assert.deepEqual(reconcileListSearch({ source: "fair", draft: "fair tax", submitted: null }, "older"), {
    source: "older", draft: "older", submitted: null,
  });
});

test("automatic money filtering removes districts when their prerequisites no longer apply", () => {
  const requirements = { district: [{ name: "office", value: "H" }, { name: "state" }] };
  for (const values of [
    [["office", "S"], ["state", "CA"], ["district", "01"]],
    [["office", "H"], ["state", ""], ["district", "01"]],
  ]) {
    assert.equal(listQuery("offset=20", values, ["office", "state", "district"], requirements).has("district"), false);
  }
  assert.equal(listQuery("", [["office", "H"], ["state", "CA"], ["district", "01"]], ["office", "state", "district"], requirements).get("district"), "01");
});
