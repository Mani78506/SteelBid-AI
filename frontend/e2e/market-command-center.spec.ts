import { test, expect } from "@playwright/test";

test("Command Center renders available market observations", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("JAYRAJ STEEL PRIVATE LIMITED").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Steel Market Intelligence" })).toBeVisible();
  await expect(page.getByText("No sourced price observations are available for this organization.")).not.toBeVisible();
  await expect(page.getByText(/SIMULATED MARKET REFERENCE — NOT LIVE VERIFIED PRICES\./).first()).toBeVisible();
  await page.getByRole("button", { name: "90D" }).click();
  await expect(page.getByRole("button", { name: "90D" })).toHaveClass(/bg-primary/);
  await page.screenshot({ path: "e2e/market-command-center.png", fullPage: true });
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.getByRole("heading", { name: "Tender Intelligence" })).toBeVisible();
  await page.screenshot({ path: "e2e/market-command-center-tablet.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await page.screenshot({ path: "e2e/market-command-center-mobile.png", fullPage: true });
});
