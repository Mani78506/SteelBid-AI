import { expect, test } from "@playwright/test";

test("Jayraj completes the persisted simulated warehouse workflow through the UI", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@jayraj.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await page.getByText("DEMO-JRS-WH-001").first().click();

  // The seeded materials are already mapped, but remain pending until this explicit UI review.
  const confirmButtons = page.getByRole("button", { name: "Confirm" });
  await expect(page.getByText("Steel materials required", { exact: false })).toBeVisible();
  for (let remaining = await confirmButtons.count(); remaining > 0; remaining -= 1) {
    await confirmButtons.first().click();
    await page.waitForTimeout(250);
  }
  await expect(page.getByText("7/7 approved", { exact: false })).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-boq-approved.png", fullPage: true });

  await page.getByRole("button", { name: "Approve BOQ requirements" }).click();
  await expect(page.getByRole("button", { name: "Generate BOM" })).toBeEnabled();
  await page.getByRole("button", { name: "Generate BOM" }).click();
  await expect(page.getByText("Inventory & shortages")).toBeVisible();
  await expect(page.getByText(/2,700 SQM short/)).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-bom-shortages.png", fullPage: true });

  const rateInputs = page.locator('input[aria-label^="Demo rate "]');
  if (await rateInputs.count()) {
    await expect(rateInputs).toHaveCount(7);
    for (let index = 0; index < 7; index += 1) await rateInputs.nth(index).fill(index === 4 ? "780" : "55000");
    await page.getByRole("button", { name: "Create Estimate" }).click();
  }
  await expect(page.getByText("Draft tender cost estimate")).toBeVisible();
  await expect(page.getByText(/Draft only — not an approved quotation/)).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-estimate.png", fullPage: true });

  await page.getByLabel("Quotation customer").selectOption({ label: "[TRAINING] Warehouse Project Customer (DEMO-JRS-CUSTOMER)" });
  await page.getByRole("button", { name: "Select Customer" }).click();
  const generateQuotation = page.getByRole("button", { name: "Generate Quotation" });
  if (await generateQuotation.isEnabled()) await generateQuotation.click();
  await expect(page.getByRole("button", { name: "Download quotation PDF" })).toBeVisible();
  await page.getByLabel("External submission reference").fill("DEMO-JRS-MANUAL-001");
  await page.getByRole("button", { name: "Record manual submission" }).click();
  await expect(page.getByText("MANUALLY_SUBMITTED")).toBeVisible();
  await page.screenshot({ path: "e2e/jayraj-training-quotation.png", fullPage: true });

  await page.reload();
  await expect(page.getByText("DEMO-JRS-WH-001").first()).toBeVisible();
});
