import { test, expect } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "admin@apex.demo";
const PASSWORD = process.env.E2E_PASSWORD ?? "SteelBid#Demo2026";

test.describe("SteelBid AI — core flow", () => {
  test("login → command center renders live KPIs", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
    // API-backed KPIs must render (not skeletons)
    await expect(page.getByText("Inventory valuation")).toBeVisible();
    await expect(page.getByText("Today's priorities")).toBeVisible();
    await expect(page.getByText("AI Daily Briefing")).toBeVisible();
  });

  test("navigation to materials shows seeded catalog", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);

    await page.getByRole("link", { name: "Materials" }).click();
    await expect(page.getByText("Material Master")).toBeVisible();
    await expect(page.getByText(/ISMB|Plate|TMT|Angle|Channel/).first()).toBeVisible();
  });

  test("inquiry → quotation → sales order chain", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/login");
    await page.getByLabel("Work email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);

    // Create inquiry
    await page.getByRole("link", { name: "Inquiries" }).click();
    await page.getByRole("button", { name: "New inquiry" }).click();
    const ref = `E2E-${Date.now()}`;
    await page.getByPlaceholder("RFQ-2026-114").fill(ref);
    // pick first customer + material + description + qty
    await page.locator("select").nth(0).selectOption({ index: 1 });
    await page.locator("select").nth(1).selectOption({ index: 1 });
    await page.getByPlaceholder("Description").fill("E2E structural steel 100 MT");
    await page.getByPlaceholder("Qty").fill("100");
    await page.getByRole("button", { name: "Record inquiry" }).click();
    await expect(page.getByText("Inquiry recorded")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(ref)).toBeVisible();
  });

  test("organization switch changes dashboard scope", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill("admin@railbuild.demo");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);

    // RailBuild admin belongs to all 4 demo orgs — switch via the topbar switcher
    await page.getByRole("button", { name: "Organization switcher" }).click();
    await page.getByRole("option", { name: /Metro Steel Distributors/ }).click();
    await expect(page.getByRole("button", { name: "Organization switcher" })).toContainText("Metro Steel Distributors");
    // tenant data changed: Metro's dashboard, not RailBuild's tenders
    await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  });

  test("logout returns to login", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.getByRole("button", { name: "User menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
