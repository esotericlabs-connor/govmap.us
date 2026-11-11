import assert from "node:assert/strict";
import { afterEach, mock, test } from "node:test";

import { healthResponse } from "../lib/health.mjs";

const sha = "a".repeat(40);
const otherSha = "b".repeat(40);
const apiBase = "http://backend:8000";

afterEach(() => mock.restoreAll());

function silenceExpectedError() {
  return mock.method(console, "error", () => {});
}

test("healthy probe is uncached, bounded and reports both commits", async () => {
  const fetch = mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, `${apiBase}/ready`);
    assert.equal(options.cache, "no-store");
    assert.equal(options.redirect, "error");
    assert.ok(options.signal instanceof AbortSignal);
    return Response.json({ status: "ok", commit_sha: sha });
  });
  const timeout = mock.method(AbortSignal, "timeout", (milliseconds) => {
    assert.equal(milliseconds, 5000);
    return new AbortController().signal;
  });
  const response = await healthResponse(`${apiBase}/`, sha);
  assert.equal(fetch.mock.callCount(), 1);
  assert.equal(timeout.mock.callCount(), 1);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), {
    status: "ok",
    commit_sha: sha,
    backend_commit_sha: sha,
  });
});

test("unknown commits remain explicitly unknown", async () => {
  mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "ok", commit_sha: null }),
  );
  const response = await healthResponse(apiBase, "unknown");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    status: "ok",
    commit_sha: null,
    backend_commit_sha: null,
  });
});

test("invalid frontend build commit fails without probing the backend", async () => {
  silenceExpectedError();
  const fetch = mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "ok", commit_sha: sha }),
  );
  const response = await healthResponse(apiBase, "main");
  assert.equal(response.status, 503);
  assert.equal(fetch.mock.callCount(), 0);
});

test("different deployed commits are unavailable", async () => {
  const log = silenceExpectedError();
  mock.method(globalThis, "fetch", async () =>
    Response.json({ status: "ok", commit_sha: otherSha }),
  );
  const response = await healthResponse(apiBase, sha);
  assert.equal(response.status, 503);
  assert.equal((await response.json()).backend_commit_sha, otherSha);
  assert.equal(log.mock.callCount(), 1);
});

for (const status of [401, 404, 500, 503]) {
  test(`backend HTTP ${status} returns unavailable`, async () => {
    silenceExpectedError();
    mock.method(globalThis, "fetch", async () =>
      Response.json({ detail: "private detail" }, { status }),
    );
    const response = await healthResponse(apiBase, sha);
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.ok(!(await response.text()).includes("private"));
  });
}

for (const body of [
  null,
  [],
  {},
  { status: "unavailable", commit_sha: sha },
  { status: "ok" },
  { status: "ok", commit_sha: "not-a-sha" },
]) {
  test(`invalid readiness payload ${JSON.stringify(body)} fails closed`, async () => {
    silenceExpectedError();
    mock.method(globalThis, "fetch", async () => Response.json(body));
    const response = await healthResponse(apiBase, sha);
    assert.equal(response.status, 503);
  });
}

test("invalid JSON fails closed", async () => {
  silenceExpectedError();
  mock.method(globalThis, "fetch", async () => new Response("<html>private</html>"));
  assert.equal((await healthResponse(apiBase, sha)).status, 503);
});

for (const name of ["TypeError", "TimeoutError", "AbortError"]) {
  test(`${name} is unavailable without exposing the exception`, async () => {
    const log = silenceExpectedError();
    mock.method(globalThis, "fetch", async () => {
      throw new DOMException("private URL and secret", name);
    });
    const response = await healthResponse(apiBase, sha);
    assert.equal(response.status, 503);
    assert.ok(!(await response.text()).includes("private"));
    assert.ok(!JSON.stringify(log.mock.calls).includes("private URL"));
  });
}
