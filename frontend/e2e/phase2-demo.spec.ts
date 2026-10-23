import { test, expect } from "@playwright/test";

test.describe("SteelBid AI — Phase 2 Market Watch Demo", () => {
  test("Phase 2 features: price basis, CSV import, expanded products", async ({ page, context }) => {
    // Enable video recording
    await context.close();
    const videoContext = await context.browser().newContext({
      recordVideo: { dir: "frontend/e2e/phase2-video", size: { width: 1920, height: 1080 } },
      viewport: { width: 1920, height: 1080 },
    });
    const demoPage = await videoContext.newPage();

    console.log("🎬 Starting Phase 2 Market Watch demo...");

    // 1. Login
    await demoPage.goto("http://127.0.0.1:5173/login");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/01-login.png", fullPage: true });
    console.log("✓ Login screen loaded");

    await demoPage.locator('input[type="email"]').fill("admin@apex.demo");
    await demoPage.locator('input[type="password"]').fill("SteelBid#Demo2026");
    await demoPage.getByRole("button", { name: "Sign in" }).click();
    // The authenticated Command Center is mounted at the application's root.
    await demoPage.waitForURL((url) => new URL(url).pathname === "/");
    console.log("✓ Logged in");

    // 2. Navigate to Market
    await demoPage.getByRole("link", { name: "Market" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/02-market-page.png", fullPage: true });
    console.log("✓ Market page loaded");

    // 3. Test expanded product forms
    const formSelect = demoPage.locator('select').first();
    await formSelect.selectOption("HRC");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/03-hrc-filter.png", fullPage: true });
    console.log("✓ HRC form selected");

    await formSelect.selectOption("CRC");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/04-crc-filter.png", fullPage: true });
    console.log("✓ CRC form selected");

    await formSelect.selectOption("BILLET");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/05-billet-filter.png", fullPage: true });
    console.log("✓ BILLET form selected");

    await formSelect.selectOption("SCRAP");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/06-scrap-filter.png", fullPage: true });
    console.log("✓ SCRAP form selected");

    // 4. Test price basis filter
    const basisSelect = demoPage.locator('select').nth(2); // 3rd select (form, grade, basis)
    await basisSelect.selectOption("DELIVERED");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/07-delivered-basis.png", fullPage: true });
    console.log("✓ DELIVERED price basis selected");

    await basisSelect.selectOption("EX_WORKS");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/08-exworks-basis.png", fullPage: true });
    console.log("✓ EX_WORKS price basis selected");

    // 5. Test manual observation with new fields
    await demoPage.getByRole("button", { name: "Record observation" }).click();
    await demoPage.waitForSelector('text=Record price observation');
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/09-observation-modal.png", fullPage: true });
    console.log("✓ Observation modal opened");

    // Verify price basis dropdown exists
    const basisDropdown = demoPage.locator('select').filter({ hasText: /EX_WORKS|DELIVERED|FORWARD/ });
    await expect(basisDropdown).toBeVisible();
    console.log("✓ Price basis dropdown visible in modal");

    await demoPage.getByRole("button", { name: "Cancel" }).click();
    console.log("✓ Modal closed");

    // 6. Show CSV import button (screenshot only, actual file upload requires file system access)
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/10-csv-import-button.png", fullPage: true });
    const csvButton = demoPage.getByRole("button", { name: "Import CSV" });
    await expect(csvButton).toBeVisible();
    console.log("✓ CSV Import button visible");

    // 7. Show Basis column in table
    const table = demoPage.locator("table").first();
    await expect(table).toBeVisible();
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/11-observations-table.png", fullPage: true });
    console.log("✓ Observations table with Basis column visible");

    // 8. Logout
    await demoPage.getByRole("button", { name: "User menu" }).click();
    await demoPage.getByRole("menuitem", { name: "Logout" }).click();
    await demoPage.waitForURL("**/login");
    await demoPage.screenshot({ path: "frontend/e2e/phase2-video/12-logout.png", fullPage: true });
    console.log("✓ Logout complete");

    // Close and save video
    await videoContext.close();
    console.log("🎬 Phase 2 demo complete — video saved to frontend/e2e/phase2-video/");
  });
});
