/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce a self-contained server bundle (.next/standalone) so the runtime
  // Docker image stays small and doesn't need the full node_modules tree.
  output: "standalone",
  images: {
    // The logos are the only images so far; skip the runtime image optimizer
    // (and its sharp dependency) until there's a real need. Revisit when
    // member photos land.
    unoptimized: true,
  },
  eslint: {
    // Lint is enforced in CI (.github/workflows/lint.yml), not as a hard gate
    // on the production build — a stray lint nit shouldn't be able to block a
    // deploy. Type checking still runs during the build.
    ignoreDuringBuilds: true,
  },
  // Proxy same-origin browser calls ("/api/*") to the backend server-side. This
  // keeps client fetches on the page's own origin so they never depend on the
  // public api.* host being reachable/unblocked from the device or on CORS —
  // the cross-origin request to api.govmap.us was what failed on mobile.
  // Resolved at runtime to the compose-internal backend when available, else
  // the public API host baked at build time, else localhost for `next dev`.
  async rewrites() {
    const apiBase =
      process.env.API_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${apiBase}/api/:path*` }];
  },
};

export default nextConfig;
