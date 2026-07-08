import { test, expect } from "@playwright/test";

/** Full-stack smoke test — requires a live backend (Postgres, Redis,
 * Qdrant, Ollama) at BACKEND_URL and `npm run dev`/`npm run build &&
 * npm start` running. Verified manually against a real stack during
 * Module 18 development (see docs/modules/frontend.md); not part of the
 * default `npm test` gate since it needs infrastructure beyond the repo,
 * mirroring the backend's own `-m integration` split. Run with:
 *   npm run e2e
 */
test("register, create workspace, register repo, search, and chat end to end", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "correct-horse-battery-staple";

  await page.goto("/");
  await page.waitForURL("**/login");

  await page.goto("/register");
  await page.fill("#full_name", "E2E Test User");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/workspaces");

  await page.fill("#name", "E2E Workspace");
  await page.click('button:has-text("Create workspace")');
  await page.waitForURL(/\/workspaces\/[0-9a-f-]+$/);
  const workspaceId = page.url().split("/workspaces/")[1];

  await page.fill("#git_url", "https://github.com/octocat/Hello-World.git");
  await page.click('button:has-text("Register repository")');
  await expect(page.locator("text=Hello-World.git").first()).toBeVisible();

  await page.locator("text=Hello-World.git").first().click();
  await page.waitForURL(/\/repositories\/[0-9a-f-]+$/);
  await expect(page.locator('[data-slot="badge"]').first()).toBeVisible();

  await page.goto(`/workspaces/${workspaceId}/search`);
  await page.fill('input[placeholder*="credit card"]', "hello world function");
  await page.click('button:has-text("Search")');
  await expect(page.locator("main")).toContainText(/No results found|score/i, { timeout: 10_000 });

  await page.goto(`/workspaces/${workspaceId}/conversations`);
  await page.click('button:has-text("New conversation")');
  await page.waitForURL(/\/conversations\/[0-9a-f-]+$/);

  await page.locator("textarea").fill("hey, thanks for your help!");
  await page.click('button:has-text("Send")');
  await expect(page.locator("main")).toContainText("hey, thanks for your help!");
  // Real Ollama generation — generous timeout for a cold model.
  await expect(page.locator("main")).not.toContainText("hey, thanks for your help!Send", {
    timeout: 30_000,
  });

  await page.click('button:has-text("Log out")');
  await page.waitForURL("**/login");
});
