import assert from "node:assert/strict";
import { test } from "node:test";

import { externalHref } from "../lib/safe-url.mjs";

test("official http(s) links pass through as normalized hrefs", () => {
  assert.equal(
    externalHref("https://www.congress.gov/119/bills/hr1/BILLS-119hr1ih.htm"),
    "https://www.congress.gov/119/bills/hr1/BILLS-119hr1ih.htm",
  );
  assert.equal(externalHref("https://VoteView.com/rollcall/RS1190001"), "https://voteview.com/rollcall/RS1190001");
  assert.equal(externalHref("http://www.house.gov"), "http://www.house.gov/");
});

test("script-capable, relative and malformed values never become links", () => {
  for (const value of [
    "javascript:alert(1)",
    " JavaScript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "mailto:someone@example.com",
    "/internal/pipeline-status",
    "//evil.example/path",
    "not a url",
    "",
    null,
    undefined,
  ]) {
    assert.equal(externalHref(value), undefined, String(value));
  }
});
