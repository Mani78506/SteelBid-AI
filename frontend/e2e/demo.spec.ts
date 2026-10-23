import { test, expect } from "@playwright/test";

test.describe("SteelBid AI — Product Demo Walkthrough", () => {
  test("2-minute steel business demo flow", async ({ page, context }) => {
    // Enable video recording for the demo
    await context.close(); // Close default context
    const videoContext = await context.browser().newContext({
      recordVideo: { dir: "frontend/e2e/demo-video", size: { width: 1920, height: 1080 } },
      viewport: { width: 1920, height: 1080 },
    });
    const demoPage = await videoContext.newPage();

    // DEMO SCRIPT
    console.log("🎬 Starting SteelBid AI product demo...");

    // 1. LOGIN SCREEN (premium industrial design)
    await demoPage.goto("https://web-production-972cd.up.railway.app/login");
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/01-login.png", fullPage: true });
    console.log("✓ Login screen loaded — premium industrial design");

    // Login as admin@apex.demo (trader org)
    await demoPage.getByLabel("Email").fill("admin@apex.demo");
    await demoPage.locator('input[type="password"]').fill("SteelBid#Demo2026");
    await demoPage.getByRole("button", { name: "Sign in" }).click();
    await demoPage.waitForURL("**/app/dashboard");
    console.log("✓ Logged in as Apex Steel Traders admin");

    // 2. STEEL BUSINESS COMMAND CENTER (the flagship)
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/02-command-center.png", fullPage: true });
    console.log("✓ Command Center — KPIs, recent inquiries, market intel");

    // Verify KPIs are live
    const kpiCards = demoPage.locator('[class*="KpiCard"]');
    await expect(kpiCards.first()).toBeVisible();
    console.log("✓ KPIs render: inventory valuation, sales orders, receivables");

    // 3. INVENTORY MODULE (real stock, heat numbers, quality states)
    await demoPage.getByRole("link", { name: "Inventory" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/03-inventory.png", fullPage: true });
    console.log("✓ Inventory — stock lots, heat numbers, quality states");

    // Verify stock lot data
    const lotsTable = demoPage.locator("table").first();
    await expect(lotsTable).toBeVisible();
    console.log("✓ Stock lots table with ISMB, plates, quality status");

    // 4. MATERIALS CATALOG (organization-specific)
    await demoPage.getByRole("link", { name: "Materials" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/04-materials.png", fullPage: true });
    console.log("✓ Materials catalog — grades, forms, standards");

    // 5. CUSTOMERS (real CRM)
    await demoPage.getByRole("link", { name: "Customers" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/05-customers.png", fullPage: true });
    console.log("✓ Customers — credit terms, GSTIN, contact details");

    // 6. INQUIRIES (the sales workflow start)
    await demoPage.getByRole("link", { name: "Inquiries" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/06-inquiries.png", fullPage: true });
    console.log("✓ Inquiries — customer requests with availability");

    // 7. QUOTATIONS (margin calculations, comparison)
    await demoPage.getByRole("link", { name: "Quotations" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/07-quotations.png", fullPage: true });
    console.log("✓ Quotations — cost vs selling, 12% margin example");

    // 8. SALES ORDERS (allocation, shortage analysis)
    await demoPage.getByRole("link", { name: "Sales Orders" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/08-sales-orders.png", fullPage: true });
    console.log("✓ Sales Orders — lot allocation, shortage analysis");

    // 9. PROCUREMENT (supplier comparison, landed cost)
    await demoPage.getByRole("link", { name: "Procurement" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/09-procurement.png", fullPage: true });
    console.log("✓ Procurement — suppliers, landed cost, comparison");

    // 10. MARKET INTELLIGENCE (synthetic but realistic structure)
    await demoPage.getByRole("link", { name: "Market" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/10-market.png", fullPage: true });
    console.log("✓ Market Intelligence — price observations (synthetic demo)");

    // 11. FABRICATION (BOMs, work orders)
    await demoPage.getByRole("link", { name: "Fabrication" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/11-fabrication.png", fullPage: true });
    console.log("✓ Fabrication — BOMs, work orders, inspections");

    // 12. TENDERS (extraction review, BOQs)
    await demoPage.getByRole("link", { name: "Tenders" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/12-tenders.png", fullPage: true });
    console.log("✓ Tenders — extraction review, BOQ item review");

    // 13. PROJECTS (project management)
    await demoPage.getByRole("link", { name: "Projects" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/13-projects.png", fullPage: true });
    console.log("✓ Projects — railway, infrastructure projects");

    // 14. LOGISTICS (dispatch planning)
    await demoPage.getByRole("link", { name: "Logistics" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/14-logistics.png", fullPage: true });
    console.log("✓ Logistics — dispatch planning, vehicle tracking");

    // 15. FINANCE (receivables, payables, valuation)
    await demoPage.getByRole("link", { name: "Finance" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/15-finance.png", fullPage: true });
    console.log("✓ Finance — receivables, payables, inventory valuation");

    // 16. AI BRIEFING (AI-powered insights)
    await demoPage.getByRole("link", { name: "AI Briefing" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/16-ai-briefing.png", fullPage: true });
    console.log("✓ AI Briefing — shortage analysis, supplier recommendations");

    // 17. Return to Command Center
    await demoPage.getByRole("link", { name: "Command Center" }).click();
    await demoPage.waitForLoadState("networkidle");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/17-command-center-final.png", fullPage: true });
    console.log("✓ Back to Command Center — complete walkthrough");

    // 18. Logout
    await demoPage.getByRole("button", { name: "User menu" }).click();
    await demoPage.getByRole("menuitem", { name: "Logout" }).click();
    await demoPage.waitForURL("**/login");
    await demoPage.screenshot({ path: "frontend/e2e/demo-video/18-logout.png", fullPage: true });
    console.log("✓ Logout — secure session termination");

    // Close and save video
    await videoContext.close();
    console.log("🎬 Demo complete — video saved to frontend/e2e/demo-video/");
  });
});
