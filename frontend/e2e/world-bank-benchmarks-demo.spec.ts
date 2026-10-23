import { expect, test } from "@playwright/test";

test("Apex can view isolated World Bank global benchmarks", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Market Prices" }).click();

  const section = page.getByText("Global Commodity Benchmarks").locator("..").locator("..");
  await expect(page.getByText("Global Commodity Benchmarks")).toBeVisible();
  await expect(page.getByText(/not Indian steel prices and not a live feed/i)).toBeVisible();
  await expect(page.getByText(/World Bank Commodity Markets, The Pink Sheet/i)).toBeVisible();
  await expect(page.getByText("CC BY 4.0 · attribution required")).toBeVisible();
  await expect(page.getByText(/USD/).first()).toBeVisible();
  await page.screenshot({ path: "e2e/world-bank-benchmarks-full.png", fullPage: true });

  const picker = section.locator("select");
  await expect(picker.locator("option")).toHaveCount(5);
  await page.getByRole("button", { name: "12M" }).click();
  await expect(page.getByRole("button", { name: "12M" })).toHaveClass(/bg-sky-700/);
  await picker.selectOption({ label: "Iron ore, cfr spot" });
  await expect(page.getByText("($/dmtu)")).toBeVisible();
  await page.screenshot({ path: "e2e/world-bank-benchmarks-iron-ore.png", fullPage: true });

  await picker.selectOption({ label: "Copper" });
  await expect(page.getByText("($/mt)")).toBeVisible();
  await page.screenshot({ path: "e2e/world-bank-benchmarks-selector.png", fullPage: true });
});
