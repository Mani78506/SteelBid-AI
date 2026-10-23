import { expect, test } from "@playwright/test";

test("Jayraj uploads a fixture tender and opens BOQ extraction", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await expect(page.getByRole("button", { name: "Upload Tender" })).toBeVisible();

  await page.getByRole("button", { name: "Upload Tender" }).click();
  await page.locator('input[type="file"]').first().setInputFiles("../backend/pytest-tmp/boq_demo.pdf");
  await expect(page.getByText("Source documents")).toBeVisible();
  await page.getByRole("button", { name: "Extract BOQ" }).click();
  await expect(page.getByText(/candidate line/)).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-upload-workflow.png", fullPage: true });
});
