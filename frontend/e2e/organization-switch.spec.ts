import { expect, test } from "@playwright/test";

test("organization switch reloads Command Center with the selected tenant data", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@railbuild.demo");
  await page.locator('input[type="password"]').fill("SteelBid#Demo2026");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();

  await page.getByRole("button", { name: "Organization switcher" }).click();
  const dashboard = page.waitForResponse((response) =>
    response.url().includes("/api/v1/dashboard/enhanced?days=30") && response.status() === 200,
  );
  await page.getByRole("option", { name: /SteelBid Market Showcase/ }).first().click();

  await expect(page.getByRole("button", { name: "Organization switcher" })).toContainText("SteelBid Market Showcase");
  const data = await (await dashboard).json();
  const shortage = data.tender_shortages.reduce((total: number, row: { shortage_qty?: string }) => total + Number(row.shortage_qty ?? 0), 0);
  expect(Number(data.inventory_breakdown.available)).toBe(75);
  expect(shortage).toBe(125);
  await expect(page.getByText("75 MT").first()).toBeVisible();
});
