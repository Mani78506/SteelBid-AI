import { expect, test } from "@playwright/test";

test("Market Intelligence uses analytics tabs and saved price alerts", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@railbuild.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Organization switcher" }).click();
  await page.getByRole("option", { name: /SteelBid Market Showcase/ }).first().click();
  await page.getByRole("link", { name: "Market Prices" }).click();

  await expect(page.getByText("Market Showcase — Simulated Market Data")).toBeVisible();
  await page.getByRole("button", { name: "1Y" }).click();
  await page.getByRole("button", { name: "Regional View" }).click();
  await expect(page.getByText("Regional comparison")).toBeVisible();
  await page.getByRole("button", { name: "Alerts" }).click();
  await expect(page.getByText("Your price alerts")).toBeVisible();
  await page.screenshot({ path: "e2e/market-intelligence-alerts.png", fullPage: true });
});
