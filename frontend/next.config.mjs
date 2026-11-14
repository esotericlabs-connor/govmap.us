/**
 * Baseline hardening on every response. The CSP is deliberately limited to
 * frame-ancestors (anti-clickjacking): a script/style policy needs nonces wired
 * through Next and the Turnstile widget, and a wrong one breaks the site.
 */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  // Exact host only (no includeSubDomains/preload) so it can't strand a subdomain.
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce a self-contained server bundle (.next/standalone) so the runtime
  // Docker image stays small and doesn't need the full node_modules tree.
  output: "standalone",
  // Don't advertise the framework in an X-Powered-By header.
  poweredByHeader: false,
  images: {
    // The logos are the only images so far; skip the runtime image optimizer
    // (and its sharp dependency) until there's a real need. Revisit when
    // member photos land.
    unoptimized: true,
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  // The map lived at /congress, then at the root; the root is now the federal
  // overview. Permanent so bookmarks and search results update; Next carries
  // the query string (e.g. ?member=) through.
  async redirects() {
    return [{ source: "/congress", destination: "/map", permanent: true }];
  },
  // Lint is enforced in CI (.github/workflows/lint.yml) via the ESLint CLI;
  // Next 16 no longer lints during `next build`. Type checking still runs.
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
