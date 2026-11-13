import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatMoneyCents,
  formatMoneyExact,
  legacyItemizationSplit,
  maxPositiveMoney,
  moneyCents,
  moneyPercent,
  moneyStackBlockCents,
  moneyStackLevels,
} from "../lib/money.mjs";
import {
  moneyCandidateAnchor,
  moneyCandidateHref,
  moneyReturnHref,
  safeMoneyReturn,
  supportsMoneyDetail,
} from "../lib/money-navigation.mjs";

test("FEC decimal strings retain exact cents without floating point", () => {
  assert.equal(moneyCents("123456789012.34"), BigInt("12345678901234"));
  assert.equal(moneyCents("-0.01"), -BigInt(1));
  assert.equal(formatMoneyExact("123456789012.34"), "$123,456,789,012.34");
  assert.equal(formatMoneyExact("-0.01"), "-$0.01");
  assert.equal(formatMoneyExact("4.1"), "$4.10");
  assert.equal(formatMoneyExact("0"), "$0.00");
  assert.equal(formatMoneyExact(null), "Not reported");
  assert.equal(formatMoneyCents(BigInt(13)), "$0.13");
});

test("invalid or imprecise amounts fail explicitly", () => {
  for (const value of ["", "NaN", "1.001", "1e3", ".01", 1, undefined]) {
    assert.throws(() => moneyCents(value), /Invalid money amount/);
  }
});

test("visual scales are bounded and use one explicit whole-cent block value", () => {
  assert.equal(maxPositiveMoney(["1.00", null, "-4.00", "1.01"]), "1.01");
  assert.equal(maxPositiveMoney([null, "0.00", "-0.01"]), null);
  assert.equal(maxPositiveMoney(["999999999999.98", "999999999999.99"]), "999999999999.99");
  assert.throws(() => maxPositiveMoney(["1.001"]), /Invalid money amount/);
  assert.equal(moneyPercent("1.00", "3.00"), 33.33);
  assert.equal(moneyPercent("999999999999.99", "999999999999.99"), 100);
  assert.equal(moneyPercent("4.00", "3.00"), 100);
  assert.equal(moneyPercent("-1.00", "3.00"), 0);
  assert.equal(moneyPercent(null, "3.00"), 0);
  assert.equal(moneyStackLevels("0.01", "999999999999.99"), 1);
  assert.equal(moneyStackLevels("1.00", "2.00"), 4);
  assert.equal(moneyStackLevels("2.00", "2.00"), 8);
  assert.equal(moneyStackLevels("3.00", "2.00"), 8);
  assert.equal(moneyStackLevels("0.00", "2.00"), 0);
  assert.equal(moneyStackLevels("1.00", "0.00"), 0);
  assert.equal(moneyStackBlockCents("1.01"), BigInt(13));
  assert.equal(moneyStackLevels("0.13", "1.01"), 1);
  assert.equal(moneyStackLevels("0.14", "1.01"), 2);
  assert.equal(moneyStackLevels("-0.01", "1.01"), 0);
  assert.equal(moneyStackBlockCents(null), null);
  assert.equal(moneyStackBlockCents("-1.00"), null);
  assert.equal(moneyStackBlockCents("999999999999.99"), BigInt("12500000000000"));
});

test("candidate links keep the finance cycle and the originating workspace filters", () => {
  const origin = "/elections?cycle=2026&state=CA&offset=50";
  const target = new URL(moneyCandidateHref("H0CA00001", 2026, origin), "https://govmap.invalid");
  assert.equal(target.pathname, "/money/H0CA00001");
  assert.equal(target.searchParams.get("cycle"), "2026");
  assert.equal(target.searchParams.get("returnTo"), origin);
  assert.equal(safeMoneyReturn(origin), origin);
  assert.equal(moneyCandidateAnchor("H0CA00001"), "candidate-H0CA00001");
  assert.equal(moneyReturnHref(origin, "H0CA00001"), `${origin}#candidate-H0CA00001`);
  assert.equal(moneyReturnHref("/money?office=H", "H0CA00001"), "/money?office=H#candidate-H0CA00001");
  assert.equal(moneyReturnHref(origin, "invalid"), origin);
  assert.equal(moneyReturnHref("//example.com", "H0CA00001"), "/money#candidate-H0CA00001");
  assert.equal(safeMoneyReturn("/money?office=H&through=2026-09-30"), "/money?office=H&through=2026-09-30");
  assert.equal(supportsMoneyDetail("S0CA00001", 2026), true);
  assert.equal(supportsMoneyDetail("H0CA00001", 2027), false);
  assert.throws(() => moneyCandidateHref("not-an-id", 2026, origin), /Invalid candidate/);
  assert.throws(() => moneyCandidateAnchor("not-an-id"), /Invalid candidate/);
});

test("candidate return links reject external or unrelated routes", () => {
  for (const value of [
    undefined,
    null,
    "//example.com",
    "https://example.com/",
    "/money/another",
    "/elections#other",
    "/money\\example",
    "/money?x=1\n",
  ]) {
    assert.equal(safeMoneyReturn(value), "/money");
  }
});

test("legacy itemization shares use both reported amounts and reject missing or negative inputs", () => {
  assert.deepEqual(legacyItemizationSplit(75, 25), { itemizedPercent: 75, unitemizedPercent: 25 });
  assert.deepEqual(legacyItemizationSplit(1, 2), { itemizedPercent: 33, unitemizedPercent: 67 });
  assert.equal(legacyItemizationSplit(null, 10), null);
  assert.equal(legacyItemizationSplit(10, null), null);
  assert.equal(legacyItemizationSplit(0, 0), null);
  assert.equal(legacyItemizationSplit(-1, 5), null);
  assert.equal(legacyItemizationSplit(Number.POSITIVE_INFINITY, 5), null);
});
