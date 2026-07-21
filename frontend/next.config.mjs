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
};

export default nextConfig;
