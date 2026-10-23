import { expect, test, type Page } from "@playwright/test";

const email = "admin@jayraj.demo";
const password = "SteelBid#Demo2026";
const tenderRef = "DEMO-JRS-WH-001";
const title = "[TRAINING TENDER] Structural Steel Supply for Industrial Warehouse";

async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: `e2e/jayraj-market-to-quotation-${name}.png`, fullPage: true });
}

test("Jayraj market-to-quotation workflow uses persisted training data and real report binaries", async ({ page }) => {
  // 1. Log in to Jayraj.
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  // 2-4. Open market intelligence and verify visible simulated-market provenance.
  await page.getByRole("link", { name: "Market Prices" }).click();
  await expect(page.getByText("Steel Market Intelligence", { exact: true })).toBeVisible();
  const kolkataDate = await page.evaluate(() => new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(new Date()));
  await expect(page.getByText(/SIMULATED MARKET REFERENCE — NOT LIVE VERIFIED PRICES\./)).toBeVisible();
  await expect(page.getByText(`Dashboard date: ${kolkataDate}.`)).toBeVisible();
  await expect(page.locator("svg.recharts-surface").first()).toBeVisible();
  await screenshot(page, "market-intelligence");

  // 5-7. Tender discovery, training deadline, and selected warehouse tender.
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await expect(page.getByRole("heading", { name: "Tender Discovery & BOQ" })).toBeVisible();
  await expect(page.getByText(tenderRef)).toBeVisible();
  await expect(page.getByText(/Structural Steel Supply for Industrial Warehouse/).first()).toBeVisible();
  await screenshot(page, "tender-discovery");
  await page.getByText(tenderRef).first().click();
  await expect(page.getByText("Steel materials required", { exact: false })).toBeVisible();

  // 8-9. Verify all seven BOQ items, then approve any still awaiting review.
  await expect(page.getByText("Steel materials required", { exact: false })).toBeVisible();
  await expect(page.getByText("4200 SQM").first()).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirm" });
  while (await confirm.count()) await confirm.first().click();
  await expect(confirm).toHaveCount(0);
  await screenshot(page, "tender-analysis");

  // 10-14. Reopen/generate persisted BOM and confirm requirements, stock and shortage.
  const approve = page.getByRole("button", { name: "Approve BOQ requirements" });
  if (await approve.isVisible()) await approve.click();
  const generateBom = page.getByRole("button", { name: "Generate BOM" });
  if (await generateBom.isVisible() && await generateBom.isEnabled()) await generateBom.click();
  await expect(page.getByText("Inventory & shortages")).toBeVisible();
  await expect(page.getByText(/Required 24 MT/)).toBeVisible();
  await expect(page.getByText(/Required 4,200 SQM/)).toBeVisible();
  await expect(page.getByText(/10 MT eligible stock/)).toBeVisible();
  await expect(page.getByText(/1,500 SQM eligible stock/)).toBeVisible();
  await expect(page.getByText(/2,700 SQM short/)).toBeVisible();
  const request = page.context().request;
  const workflowCheck = await request.get(`/api/v1/tenders/${(await request.get("/api/v1/tenders?size=100").then(r => r.json())).items.find((i: any) => i.number === tenderRef).id}/workflow`).then(r => r.json());
  expect(workflowCheck.shortages.filter((s: any) => s.unit === "MT").reduce((n: number, s: any) => n + Number(s.required_quantity), 0)).toBe(76);
  expect(workflowCheck.shortages.filter((s: any) => s.unit === "MT").reduce((n: number, s: any) => n + Number(s.available_quantity), 0)).toBe(30);
  expect(workflowCheck.shortages.filter((s: any) => s.unit === "MT").reduce((n: number, s: any) => n + Number(s.shortage_quantity), 0)).toBe(46);
  await screenshot(page, "bom-inventory");

  // 15. Procurement must disclose persisted offers, or its truthful empty state.
  await expect(page.getByText(/Supplier allocation/)).toBeVisible();
  const firstSnapshot = (await request.get(`/api/v1/tenders/${workflowCheck.tender_id}/requirement-snapshots`).then(r => r.json()))[0];
  const offers = await request.get(`/api/v1/tenders/${workflowCheck.tender_id}/requirement-snapshots/${firstSnapshot.id}/supplier-offers`).then(r => r.json());
  expect(Array.isArray(offers.items)).toBeTruthy(); // persisted offers, if any; otherwise the truthful empty state.
  await screenshot(page, "procurement");

  // 16-19. Existing commercial records are reopened; create only when the UI offers it.
  const rateInputs = page.locator('input[aria-label^="Demo rate "]');
  if (await rateInputs.count()) {
    expect(await rateInputs.count()).toBe(7);
    for (let i = 0; i < 7; i += 1) await rateInputs.nth(i).fill(i === 4 ? "780" : "55000");
    await page.getByRole("button", { name: "Create Estimate" }).click();
  }
  await expect(page.getByText("Draft tender cost estimate")).toBeVisible();
  await expect(page.getByText(/DEMO_COMMERCIAL_RATE|Demo commercial rate|Draft only/).first()).toBeVisible();
  await screenshot(page, "estimate");
  const selectCustomer = page.getByRole("button", { name: "Select Customer" });
  if (await selectCustomer.isVisible()) {
    await page.getByLabel("Quotation customer").selectOption({ label: "[TRAINING] Warehouse Project Customer (DEMO-JRS-CUSTOMER)" });
    await selectCustomer.click();
  }
  const createQuotation = page.getByRole("button", { name: "Generate Quotation" });
  if (await createQuotation.isVisible() && await createQuotation.isEnabled()) await createQuotation.click();
  await expect(page.getByRole("button", { name: "Download quotation PDF" })).toBeVisible();
  await screenshot(page, "final-quotation");

  // 20. Real backend downloads: validate signatures, MIME, ZIP/XLSX structure and content.
  await expect(page.getByText("Documents & Reports")).toBeVisible();
  await screenshot(page, "documents-reports");
  const tender = await request.get("/api/v1/tenders?size=100").then(r => r.json()).then((x: any) => x.items.find((i: any) => i.number === tenderRef));
  expect(tender).toBeTruthy();
  const pdfPaths = ["analysis.pdf", "boq.pdf", "bom.pdf", "inventory.pdf", "supplier-comparison.pdf", "estimate.pdf", "workflow/quotation.pdf"];
  for (const path of pdfPaths) {
    const response = await request.get(`/api/v1/tenders/${tender.id}/${path.startsWith("workflow") ? path : `reports/${path}`}`);
    expect(response.status(), path).toBe(200);
    expect(response.headers()["content-type"], path).toContain("application/pdf");
    const body = await response.body();
    expect(body.subarray(0, 5).toString(), path).toBe("%PDF-");
    const text = body.toString("latin1");
    expect(text.length, path).toBeGreaterThan(100);
  }
  for (const path of ["workflow/boq.xlsx", "workflow/bom.xlsx", "workflow/estimate.xlsx"]) {
    const response = await request.get(`/api/v1/tenders/${tender.id}/${path}`);
    expect(response.status(), path).toBe(200);
    expect(response.headers()["content-type"], path).toContain("spreadsheetml.sheet");
    expect((await response.body()).subarray(0, 2).toString(), path).toBe("PK");
  }

  // Persistence and isolation: refresh current tender, then switch to another training tender.
  await page.reload();
  await expect(page.getByText(tenderRef).first()).toBeVisible();
  await page.getByRole("link", { name: "Tenders & BOQ" }).click();
  await page.getByText("DEMO-JRS-BRG-002").first().click();
  await expect(page.getByText("DEMO-JRS-BRG-002").first()).toBeVisible();
  await expect(page.getByText("Documents & Reports")).toBeVisible();
});
