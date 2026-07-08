import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a minimal, self-contained server (.next/standalone) with only
  // the production dependencies actually used — Dockerfile copies just
  // that output rather than the full node_modules tree.
  output: "standalone",
};

export default nextConfig;
