import { expect, test } from "@playwright/test";

async function signInToShowcase(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@railbuild.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Organization switcher" }).click();
  await page.getByRole("option", { name: /SteelBid Market Showcase/ }).first().click();
}

test("Showcase polished supplier, costing and market-alert flow", async ({ page }) => {
  await signInToShowcase(page);

  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await page.getByText("TND-DEMO-200MT").click();
  const estimateTitle = page.getByText("Draft tender cost estimate");
  await expect(estimateTitle).toBeVisible();
  await expect(page.getByText("Draft only — not an approved quotation.")).toBeVisible();
  await estimateTitle.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "e2e/demo-tender-costing.png", fullPage: true });

  await page.getByRole("button", { name: "Compare supplier offers" }).first().click();
  await expect(page.getByRole("heading", { name: /Supplier comparison/ })).toBeVisible();
  await expect(page.getByText("Total landed")).toBeVisible();
  await page.screenshot({ path: "e2e/demo-supplier-comparison.png", fullPage: true });
  await page.getByRole("dialog").last().getByLabel("Close").click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await page.getByRole("dialog").first().getByLabel("Close").click();

  await page.getByText("TND-DEMO-WH-Q1").click();
  const benchmark = page.getByText("Historical market benchmark");
  await expect(benchmark).toBeVisible();
  await benchmark.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "e2e/demo-tender-benchmark.png", fullPage: true });
  await page.getByRole("dialog").first().getByLabel("Close").click();

  await page.getByRole("link", { name: "Market Prices" }).click();
  await page.getByRole("button", { name: "1Y" }).click();
  await page.screenshot({ path: "e2e/demo-quarterly-market-history.png", fullPage: true });
  await page.getByRole("button", { name: "Alerts" }).click();
  await page.getByRole("button", { name: "Run simulated alert demo" }).click();
  await expect(page.getByText("Synthetic Showcase observation replayed through the ingestion pipeline.")).toBeVisible();
  await page.screenshot({ path: "e2e/demo-alert-trigger.png", fullPage: true });

  await page.getByRole("button", { name: "Notifications" }).click();
  await expect(page.getByText("Price alert: HRC E250").first()).toBeVisible();
  await page.screenshot({ path: "e2e/demo-notification-drawer.png", fullPage: true });
});
