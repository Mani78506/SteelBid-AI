import { expect, test } from "@playwright/test";

test("Jayraj uploads the authentic ISRO structural-platform tender and preserves extraction outcome", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await page.getByRole("button", { name: "Upload Tender" }).click();
  await page.locator('input[type="file"]').first().setInputFiles("../backend/pytest-tmp/official-source/1778CPP_04022026.pdf");
  await expect(page.getByText("1778CPP_04022026.pdf")).toBeVisible();
  await page.getByRole("button", { name: "Extract BOQ" }).click();
  await expect(page.getByText(/candidate line/)).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: "e2e/isro-authentic-tender-upload.png", fullPage: true });
});
