import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import vm from "node:vm";

import {
  parseThemeChoice,
  resolveTheme,
  THEME_CHOICES,
  THEME_SCRIPT,
  THEME_STORAGE_KEY,
} from "../lib/theme.mjs";

test("only light and dark are explicit choices; anything else follows the system", () => {
  assert.deepEqual([...THEME_CHOICES], ["system", "light", "dark"]);
  for (const choice of THEME_CHOICES) assert.equal(parseThemeChoice(choice), choice);
  for (const value of [null, undefined, "", "Dark", "auto", " light", 1, {}]) {
    assert.equal(parseThemeChoice(value), "system");
  }
});

test("system resolves from the OS preference and an explicit choice overrides it", () => {
  assert.equal(resolveTheme("system", true), "dark");
  assert.equal(resolveTheme("system", false), "light");
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("dark", false), "dark");
});

test("navigation blade and mobile search use the shared theme", async () => {
  const header = await readFile(new URL("../components/SiteHeader.tsx", import.meta.url), "utf8");
  const dialog = header.match(/<dialog\b[\s\S]*?<\/dialog>/)?.[0];
  assert.ok(dialog, "navigation dialog exists");
  const classes = dialog.match(/className="([^"]*\bnavigation-dialog\b[^"]*)"/)?.[1]?.split(/\s+/);
  assert.ok(classes, "navigation dialog has classes");
  for (const name of ["bg-panel", "text-ink", "border-line", "dark:bg-[#070b1a]"]) {
    assert.ok(classes.includes(name), `navigation dialog needs ${name}`);
  }
  assert.ok(!classes.includes("chrome"), "navigation must not opt out of the selected theme");
  assert.match(header, /active\s*\?\s*"bg-sunken text-ink dark:bg-ink\/10"/);
  assert.match(dialog, /<UniversalSearch onNavigate=\{close\} \/>/);
  assert.match(dialog, /\btext-ink-soft\b/);
  assert.match(dialog, /\btext-ink-muted\b/);
});

/** Runs the first-paint script against a stand-in document and storage. */
function runThemeScript(stored, { blocked = false } = {}) {
  const dataset = {};
  const keys = [];
  vm.runInNewContext(THEME_SCRIPT, {
    document: { documentElement: { dataset } },
    localStorage: {
      getItem(key) {
        keys.push(key);
        if (blocked) throw new Error("SecurityError");
        return stored;
      },
    },
  });
  return { dataset, keys };
}

test("the first-paint script applies only a valid saved choice", () => {
  assert.deepEqual(runThemeScript("dark"), { dataset: { theme: "dark" }, keys: [THEME_STORAGE_KEY] });
  assert.deepEqual(runThemeScript("light").dataset, { theme: "light" });
  assert.deepEqual(runThemeScript(null).dataset, {});
  assert.deepEqual(runThemeScript("system").dataset, {});
  assert.deepEqual(runThemeScript('"><img src=x>').dataset, {});
});

test("the first-paint script leaves the system theme when storage is blocked", () => {
  const { dataset, keys } = runThemeScript("dark", { blocked: true });
  assert.deepEqual(dataset, {});
  assert.deepEqual(keys, [THEME_STORAGE_KEY]);
});

test("the first-paint script defines no globals", () => {
  const context = {
    document: { documentElement: { dataset: {} } },
    localStorage: { getItem: () => "dark" },
  };
  vm.runInNewContext(THEME_SCRIPT, context);
  assert.deepEqual(Object.keys(context).sort(), ["document", "localStorage"]);
});
