import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a minimal .next/standalone server for the Docker image
  // (Phase 13) — a small, self-contained output instead of needing the
  // full node_modules tree in the final image.
  output: "standalone",
};

export default nextConfig;
