// Next.js resolves the real `server-only` package specially at
// build time (it throws if bundled into a client component). Vitest
// runs outside that build pipeline, so vitest.config.ts aliases the
// import here instead — a no-op is exactly what's needed for tests,
// since everything under test already only runs server-side.
export {};
