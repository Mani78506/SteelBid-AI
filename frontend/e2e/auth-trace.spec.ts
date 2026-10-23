import { test } from "@playwright/test";

test("trace Jayraj authentication", async ({ page }) => {
  page.on("console", (m) => console.log(`console:${m.type()}:${m.text()}`));
  page.on("pageerror", (e) => console.log(`pageerror:${e.message}`));
  page.on("response", async (r) => {
    if (r.url().includes("/api/")) console.log(`api:${r.request().method()}:${r.status()}:${r.url()}:${await r.text().catch(() => "")}`);
  });
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForTimeout(3000);
});
