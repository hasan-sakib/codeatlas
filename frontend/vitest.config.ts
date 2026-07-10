import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next", "e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Next.js resolves this build-time sentinel specially; plain
      // Vite/Vitest doesn't know it at all. See test-stubs/server-only.ts.
      "server-only": path.resolve(__dirname, "test-stubs/server-only.ts"),
    },
  },
});
