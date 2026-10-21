import { test, expect } from "@playwright/test";

test("Command Center uses the enhanced dashboard API without fallback", async ({ page }) => {
  const enhanced = page.waitForResponse((response) =>
    response.url().includes("/api/v1/dashboard/enhanced?days=30") && response.status() === 200,
  );
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await enhanced;
  await expect(page.getByRole("heading", { name: "Steel Market Intelligence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tender Intelligence" })).toBeVisible();
  await expect(page.getByRole("button", { name: "30D" })).toBeVisible();
});
