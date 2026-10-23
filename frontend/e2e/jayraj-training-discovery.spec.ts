import { expect, test } from "@playwright/test";

test("Jayraj shows only clearly-labelled training opportunities and their persisted BOQ", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.getByRole("link", { name: "Market Prices" }).click();
  await expect(page.getByText("Steel Market Intelligence", { exact: true })).toBeVisible();
  await expect(page.getByText(/DEMO \/ SIMULATED/)).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-market-start.png", fullPage: true });

  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await expect(page.getByRole("heading", { name: "Tender Discovery & BOQ" })).toBeVisible();
  const trainingReferences = await page.locator("text=/DEMO-JRS-(WH|BRG|FAB|BLD|IND|RLY)-00[1-6]/").allTextContents();
  expect(new Set(trainingReferences).size).toBe(6);
  await expect(page.getByText(/SIMULATED — not a live government opportunity/).first()).toBeVisible();
  await expect(page.getByText("DEMO-JRS-WH-001")).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-discovery.png", fullPage: true });

  await page.getByText("DEMO-JRS-WH-001").click();
  await expect(page.getByText("Steel materials required", { exact: false })).toBeVisible();
  await expect(page.getByText("ISMB 300 E250 structural beams, IS 2062").first()).toBeVisible();
  await expect(page.getByText("4200 SQM").first()).toBeVisible();
  await expect(page.getByText("SIMULATED TRAINING SCHEDULE").first()).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-analysis.png", fullPage: true });
});
