/**
 * @param {unknown} value
 * @returns {value is string}
 */
function isCommit(value) {
  return typeof value === "string" && /^[a-f0-9]{40}$/.test(value);
}

/**
 * @param {string} apiBase
 * @param {string | undefined} buildCommit
 * @returns {Promise<Response>}
 */
export async function healthResponse(apiBase, buildCommit) {
  const commit = isCommit(buildCommit) ? buildCommit : null;
  let backendCommit = null;
  let ready = false;
  try {
    if (buildCommit !== undefined && buildCommit !== "unknown" && !isCommit(buildCommit)) {
      throw new Error("InvalidBuildCommit");
    }
    const response = await fetch(`${apiBase.replace(/\/$/, "")}/ready`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      throw new Error("BackendUnavailable");
    }
    /** @type {unknown} */
    const body = await response.json();
    if (
      body === null ||
      typeof body !== "object" ||
      !("status" in body) ||
      !("commit_sha" in body) ||
      body.status !== "ok" ||
      !(body.commit_sha === null || isCommit(body.commit_sha))
    ) {
      throw new Error("InvalidHealthResponse");
    }
    backendCommit = body.commit_sha;
    if (commit !== null && backendCommit !== null && commit !== backendCommit) {
      throw new Error("DeploymentMismatch");
    }
    ready = true;
  } catch {
    // Never log upstream URLs, response bodies or credential-bearing errors.
    console.error("Frontend health check failed: readiness or release identity unavailable or invalid");
  }
  return Response.json(
    {
      status: ready ? "ok" : "unavailable",
      commit_sha: commit,
      backend_commit_sha: backendCommit,
    },
    {
      status: ready ? 200 : 503,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
