import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

const sha = "a".repeat(40);

test("built standalone health route reflects backend readiness and release mismatch", {
  timeout: 45000,
}, async () => {
  let backendStatus = 200;
  let backendCommit = sha;
  const backend = createServer((request, response) => {
    assert.equal(request.url, "/ready");
    response.writeHead(backendStatus, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      status: backendStatus === 200 ? "ok" : "unavailable",
      commit_sha: backendCommit,
    }));
  });
  backend.listen(0, "127.0.0.1");
  await once(backend, "listening");
  const address = backend.address();
  assert.ok(address && typeof address === "object");
  const child = spawn(process.execPath, [".next/standalone/server.js"], {
    env: {
      ...process.env,
      PORT: "3100",
      HOSTNAME: "127.0.0.1",
      APP_COMMIT_SHA: sha,
      API_INTERNAL_URL: `http://127.0.0.1:${address.port}`,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let logs = "";
  child.stdout.on("data", (chunk) => { logs += chunk.toString(); });
  child.stderr.on("data", (chunk) => { logs += chunk.toString(); });
  const exited = once(child, "exit");
  const probe = () => fetch("http://127.0.0.1:3100/health", {
    signal: AbortSignal.timeout(1000),
    redirect: "error",
  });
  try {
    let started = false;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      assert.equal(child.exitCode, null, `Standalone server exited:\n${logs}`);
      try {
        const response = await probe();
        await response.arrayBuffer();
        started = true;
        break;
      } catch {
        await delay(100);
      }
    }
    assert.ok(started, `Standalone server did not become responsive:\n${logs}`);
    const healthy = await probe();
    assert.equal(healthy.status, 200);
    assert.equal(healthy.headers.get("cache-control"), "no-store");
    assert.deepEqual(await healthy.json(), {
      status: "ok", commit_sha: sha, backend_commit_sha: sha,
    });

    backendStatus = 503;
    const unavailable = await probe();
    assert.equal(unavailable.status, 503);
    assert.equal((await unavailable.json()).status, "unavailable");

    backendStatus = 200;
    backendCommit = "b".repeat(40);
    assert.equal((await probe()).status, 503);

    backendCommit = sha;
    assert.equal((await probe()).status, 200);

    backend.closeAllConnections();
    await new Promise((resolve) => backend.close(resolve));
    assert.equal((await probe()).status, 503);
  } finally {
    child.kill("SIGTERM");
    await exited;
    if (backend.listening) {
      backend.closeAllConnections();
      await new Promise((resolve) => backend.close(resolve));
    }
  }
});
