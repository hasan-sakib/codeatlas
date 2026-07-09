import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a minimal, self-contained server (.next/standalone) with only
  // the production dependencies actually used — Dockerfile copies just
  // that output rather than the full node_modules tree.
  output: "standalone",
  experimental: {
    // On by default since Next 16.1 — Turbopack persists a RocksDB-like
    // store under .next/dev/cache/turbopack between dev sessions. Under
    // this project's Docker setup it corrupted itself repeatedly
    // ("Compaction failed: Another write batch or compaction is already
    // active", then "Unable to open static sorted file" even after a
    // full cache wipe and moving it to tmpfs) and broke server actions
    // (login included) with the resulting requests 500ing. Disabling it
    // trades away cross-restart dev rebuild speed for a dev server that
    // doesn't corrupt itself; production builds are unaffected.
    turbopackFileSystemCacheForDev: false,
  },
};

export default nextConfig;
