import { expect, test } from "@playwright/test";

test("Showcase customer-demo readiness flow", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@railbuild.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Organization switcher" }).click();
  await page.getByRole("option", { name: /SteelBid Market Showcase/ }).first().click();

  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByText("75 MT").first()).toBeVisible();
  await expect(page.getByText("125 MT").first()).toBeVisible();
  await page.screenshot({ path: "e2e/demo-command-center.png", fullPage: true });

  await page.getByRole("link", { name: "Market Prices" }).click();
  await expect(page.getByText("Market Showcase — Simulated Market Data")).toBeVisible();
  await page.getByRole("button", { name: "Regional View" }).click();
  await expect(page.getByText("Regional comparison")).toBeVisible();
  await page.getByRole("button", { name: "Movers" }).click();
  await expect(page.getByText(/Largest increases/)).toBeVisible();
  await page.screenshot({ path: "e2e/demo-market-intelligence.png", fullPage: true });

  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await page.getByText("TND-DEMO-200MT").click();
  await expect(page.getByText("Material requirements vs stock")).toBeVisible();
  await expect(page.getByText(/100 MT/).first()).toBeVisible();
  await expect(page.getByText(/60 MT/).first()).toBeVisible();
  await expect(page.getByText("Supplier allocations")).toBeVisible();
  await page.screenshot({ path: "e2e/demo-tender-detail.png", fullPage: true });
});
