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
};

export default nextConfig;
