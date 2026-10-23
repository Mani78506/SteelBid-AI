import { expect, test } from "@playwright/test";

test("Tender detail prioritises persisted project and extracted steel requirements", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  const row = page.locator("tbody tr").filter({ hasText: "boq_demo" }).first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByText("Steel materials required", { exact: false })).toBeVisible();
  await expect(page.getByText("Extracted lines", { exact: true })).toBeVisible();
  await expect(page.getByText("Extracted material lines", { exact: false })).toBeVisible();
  await page.screenshot({ path: "e2e/tender-detail-analysis.png", fullPage: true });
});
