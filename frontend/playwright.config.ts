import { defineConfig } from "@playwright/test";

/** Full-stack e2e smoke tests — require a real backend (Postgres, Redis,
 * Qdrant, Ollama) reachable at BACKEND_URL and this app's dev server
 * running. Not run as part of `npm test`/CI's default gate for the same
 * reason the backend's own `-m integration` suite isn't: it needs live
 * infrastructure, not just the repo. See frontend/README.md. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
});
