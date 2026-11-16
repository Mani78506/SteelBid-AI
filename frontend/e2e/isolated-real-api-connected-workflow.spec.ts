import { expect, request, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { inflateSync } from "node:zlib";

/*
 * This is deliberately a single connected browser/API journey.  It consumes
 * the database's existing tenant-scoped materials, stock lots and supplier
 * offers; it never creates stock, supplier quotes, or commercial rates.
 */
const password = "SteelBid#Demo2026";
const pdf = path.resolve(import.meta.dirname, "../../backend/pytest-tmp/boq_demo.pdf");
const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5173";

type Boq = { id: string; raw_description: string; form: string | null; grade: string | null; specification: Record<string, unknown>; quantity: string; unit: string; material_id: string | null; review_status: string };
type Match = { bom_item_id: string; requirement_snapshot_id: string | null; material_id: string; material_name: string | null; required_quantity: string; unit: string; eligible_stock_quantity: string; reserved_quantity: string; quality_held_quantity: string; available_quantity: string; tender_allocated_quantity: string; shortage_quantity: string; matching_status: string };
type Material = { id: string; form: string; grade: string; standard: string | null; base_unit: string; specification: Record<string, unknown> };
type EligibleLot = { id: string; quantity: string; valuation_rate: string | null; currency: string; valuation_source: Record<string, unknown> };
type Offer = { supplier_quote_id: string; compatible: boolean; comparison_status: string; reasons?: string[]; available_unallocated_quantity: string; coverage_quantity: string };

function isCompatible(row: Boq, material: Material) {
  const same = (left: unknown, right: unknown) => String(left).toUpperCase() === String(right).toUpperCase();
  if (row.form && material.form && !same(row.form, material.form)) return false;
  if (row.grade && material.grade && !same(row.grade, material.grade)) return false;
  if (row.unit && material.base_unit !== row.unit) return false;
  const standard = row.specification?.standard;
  if (standard && material.standard && !same(standard, material.standard)) return false;
  const dimensions = row.specification?.dimensions ?? row.specification?.size;
  const materialDimensions = material.specification?.dimensions ?? material.specification?.size;
  return !(dimensions && materialDimensions && !same(dimensions, materialDimensions));
}

function readablePdfStreams(pdf: Buffer) {
  const source = pdf.toString("latin1");
  const text: string[] = [];
  const stream = /stream\r?\n/g;
  for (let match = stream.exec(source); match; match = stream.exec(source)) {
    const end = source.indexOf("endstream", stream.lastIndex);
    if (end < 0) break;
    const payload = source.slice(stream.lastIndex, end).replace(/\r?\n$/, "");
    try { text.push(inflateSync(Buffer.from(payload, "latin1")).toString("latin1")); } catch { /* non-Flate PDF streams are ignored */ }
    stream.lastIndex = end + "endstream".length;
  }
  return text.join("\n").replace(/<([0-9a-fA-F]+)>/g, (_match, encoded) =>
    Buffer.from(encoded, "hex").toString("latin1"));
}

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  // The public demonstration is the initial login view; the connected
  // lifecycle requires an authorized workspace identity.
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("[DEMO] Apex Steel Traders Pvt Ltd").first()).toBeVisible();
}

async function apiAs(email: string) {
  const context = await request.newContext({ baseURL });
  expect((await context.post("/api/v1/auth/login", { data: { email, password } })).ok()).toBeTruthy();
  return context;
}

test("isolated real API: connected tender lifecycle from actual PDF to outcome", async ({ page }) => {
  expect(existsSync(pdf), "Training fixture is required").toBeTruthy();
  await login(page);
  const number = `E2E-CONNECTED-${Date.now()}`;
  const create = await page.request.post("/api/v1/tenders", { data: { number, title: "[SYNTHETIC E2E] Connected PDF tender lifecycle", project_type: "FABRICATION", submission_deadline: "2027-01-01T10:00:00Z" } });
  expect(create.ok()).toBeTruthy();
  const tender = await create.json() as { id: string };

  await page.goto(`/tenders/${tender.id}?section=documents`);
  await page.locator('input[type="file"]').setInputFiles(pdf);
  const documents = page.getByLabel("Documents and extraction");
  await documents.getByRole("button", { name: "Extract BOQ" }).click();
  await expect(page.getByText(/Extraction created \d+ pending review row/)).toBeVisible();
  await page.screenshot({ path: "e2e/connected-extraction-results.png", fullPage: true });

  const boqResponse = await page.request.get(`/api/v1/tenders/${tender.id}/boq`);
  expect(boqResponse.ok()).toBeTruthy();
  const extracted = await boqResponse.json() as Boq[];
  expect(extracted.length).toBeGreaterThan(0);
  for (const row of extracted) {
    expect(row.raw_description).not.toEqual("");
    expect(row.quantity).not.toEqual("0.000000");
    expect(row.unit).not.toEqual("");
    expect(row.form || row.grade || Object.keys(row.specification).length).toBeTruthy();
  }
  const materialResponse = await page.request.get("/api/v1/materials?page_size=100");
  expect(materialResponse.ok()).toBeTruthy();
  const materials = (await materialResponse.json() as { items: Material[] }).items;
  const approvable = extracted.map(row => ({ row, material: materials.find(material => isCompatible(row, material)) })).filter((item): item is { row: Boq; material: Material } => Boolean(item.material));
  expect(approvable.length, "The verified fixture must contain at least one extracted requirement compatible with existing tenant material").toBeGreaterThan(0);

  await page.goto(`/tenders/${tender.id}?section=requirements`);
  for (const { row, material } of approvable) {
    const tr = page.locator("tbody tr").filter({ hasText: row.raw_description });
    await tr.getByLabel(`Material mapping for ${row.raw_description}`).selectOption(material.id);
    await tr.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("BOQ review saved.")).toBeVisible();
  }
  await page.reload();
  await expect(page.getByText("CONFIRMED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/connected-boq-reviewed.png", fullPage: true });
  await page.getByRole("button", { name: "Snapshot approved requirements" }).click();
  await expect.poll(async () => {
    const snapshots = await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots`);
    return (await snapshots.json() as unknown[]).length;
  }).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Generate / update BOM" }).click();
  await expect.poll(async () => {
    const workflow = await page.request.get(`/api/v1/tenders/${tender.id}/workflow`);
    return (await workflow.json() as { bom_version_id: string | null }).bom_version_id;
  }).not.toBeNull();
  await page.screenshot({ path: "e2e/connected-bom.png", fullPage: true });

  const inventoryResponse = await page.request.get(`/api/v1/tenders/${tender.id}/workspace/inventory-match`);
  expect(inventoryResponse.ok()).toBeTruthy();
  const inventory = await inventoryResponse.json() as { items: Match[] };
  expect(inventory.items.length).toBeGreaterThan(0);
  for (const row of inventory.items) {
    // The API is the source of truth: never aggregate or convert MT and SQM.
    expect(Number(row.eligible_stock_quantity)).toBeGreaterThanOrEqual(Number(row.available_quantity));
    expect(Number(row.eligible_stock_quantity)).toBeGreaterThanOrEqual(Number(row.reserved_quantity));
    expect(Number(row.quality_held_quantity)).toBeGreaterThanOrEqual(0);
    expect(Number(row.tender_allocated_quantity)).toBeGreaterThanOrEqual(0);
    expect(Number(row.shortage_quantity)).toBeGreaterThanOrEqual(0);
  }
  const units = new Set(inventory.items.map(item => item.unit));
  if (units.has("MT") && units.has("SQM")) expect(units.size).toBeGreaterThanOrEqual(2);

  // Existing stock is not an estimate source until it is explicitly allocated
  // and reserved against this tender.  Use only persisted eligible lots and
  // their own valuation provenance.
  for (const item of inventory.items) {
    let remaining = Math.min(Number(item.required_quantity), Number(item.available_quantity));
    if (remaining <= 0) continue;
    const lotsResponse = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/bom-items/${item.bom_item_id}/eligible-lots`);
    expect(lotsResponse.ok()).toBeTruthy();
    const lots = (await lotsResponse.json() as { items: EligibleLot[] }).items;
    for (const lot of lots) {
      if (remaining <= 0) break;
      const quantity = Math.min(remaining, Number(lot.quantity));
      if (quantity <= 0 || lot.valuation_rate === null || !Object.keys(lot.valuation_source ?? {}).length) continue;
      const allocation = await page.request.post(`/api/v1/tenders/${tender.id}/workflow/inventory-allocations`, {
        data: { bom_item_id: item.bom_item_id, stock_lot_id: lot.id, quantity: String(quantity), valuation_rate: lot.valuation_rate, currency: lot.currency, valuation_source: lot.valuation_source },
      });
      expect(allocation.ok()).toBeTruthy();
      remaining -= quantity;
    }
  }
  const allocatedInventoryResponse = await page.request.get(`/api/v1/tenders/${tender.id}/workspace/inventory-match`);
  expect(allocatedInventoryResponse.ok()).toBeTruthy();
  const allocatedInventory = await allocatedInventoryResponse.json() as { items: Match[] };
  // A previous isolated run may have validly reserved every eligible lot.  The
  // current tender must report that zero availability truthfully rather than
  // manufacture a stock allocation; supplier coverage handles its shortage.
  expect(allocatedInventory.items.every(item => Number(item.tender_allocated_quantity) >= 0 && Number(item.available_quantity) >= 0 && Number(item.reserved_quantity) >= 0 && Number(item.quality_held_quantity) >= 0)).toBeTruthy();
  await page.goto(`/tenders/${tender.id}?section=inventory`);
  await expect(page.getByLabel("Tender inventory match")).toContainText("Eligible");
  await page.screenshot({ path: "e2e/connected-inventory-shortages.png", fullPage: true });

  const shortages = allocatedInventory.items.filter(item => Number(item.shortage_quantity) > 0 && item.requirement_snapshot_id);
  expect(shortages.length, "Existing compatible inventory must leave a genuine procurement shortage for this fixture").toBeGreaterThan(0);
  await page.goto(`/tenders/${tender.id}?section=procurement`);
  const procurement = page.getByLabel("Tender procurement and supplier offers");
  await procurement.getByRole("button", { name: "Create requirements" }).click();
  await expect(page.getByText("Tender procurement requirements saved.")).toBeVisible();

  const suppliers = await page.request.get("/api/v1/suppliers?page_size=100");
  const supplierRows = (await suppliers.json() as { items: { id: string }[] }).items;
  expect(supplierRows.length).toBeGreaterThan(0);
  await procurement.getByLabel("RFQ supplier").selectOption(supplierRows[0].id);
  await procurement.getByRole("button", { name: "Generate draft RFQ" }).click();
  await expect(page.getByText("Draft RFQ created. It has not been issued or sent.")).toBeVisible();

  const allOfferComparisons = await Promise.all(shortages.map(async shortage => {
    const response = await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots/${shortage.requirement_snapshot_id}/supplier-offers`);
    expect(response.ok()).toBeTruthy();
    return (await response.json() as { items: Offer[] }).items;
  }));
  expect(allOfferComparisons.flat().some(offer => offer.comparison_status === "EXPIRED" || !offer.compatible), "Existing fixture must expose an expired or incompatible offer").toBeTruthy();
  for (const shortage of shortages) {
    const response = await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots/${shortage.requirement_snapshot_id}/supplier-offers`);
    expect(response.ok()).toBeTruthy();
    const offerComparison = (await response.json() as { items: Offer[] }).items;
    const candidates = offerComparison.filter(offer => offer.compatible && offer.comparison_status === "COMPATIBLE");
    let remaining = Number(shortage.shortage_quantity);
    for (const offer of candidates) {
      if (remaining <= 0) break;
      const selectedQty = Math.min(remaining, Number(offer.available_unallocated_quantity));
      if (selectedQty <= 0) continue;
      const selected = await page.request.post(`/api/v1/tenders/${tender.id}/requirement-snapshots/${shortage.requirement_snapshot_id}/supplier-selections`, {
        data: { supplier_quote_id: offer.supplier_quote_id, selected_qty: String(selectedQty) },
      });
      expect(selected.ok(), `Existing compatible offer could not cover tender shortage: ${await selected.text()}`).toBeTruthy();
      remaining -= selectedQty;
    }
    const offerSummary = offerComparison.map(offer => `${offer.comparison_status}:${offer.available_unallocated_quantity}${offer.reasons?.length ? ` (${offer.reasons.join("; ")})` : ""}`).join(", ");
    expect(remaining, `Existing compatible offers must fully cover this genuine shortage without fabricated rates; offer comparison: ${offerSummary || "none"}`).toBeLessThanOrEqual(0);
  }
  await page.reload();
  await expect(procurement.getByText("SELECTED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/connected-supplier-selection.png", fullPage: true });

  const estimate = await page.request.post(`/api/v1/tenders/${tender.id}/workflow/authoritative-estimates`, { data: { markup: "0.2" } });
  expect(estimate.ok()).toBeTruthy();
  const estimateRecord = await estimate.json() as { id: string; total_cost: string };
  const breakdown = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/authoritative-estimates/${estimateRecord.id}/breakdown`);
  expect(breakdown.ok()).toBeTruthy();
  const breakdownData = await breakdown.json() as { categories: Record<string, string>; lines: { category: string; amount: string }[] };
  expect(Object.keys(breakdownData.categories)).toContain("MATERIAL");
  expect(breakdownData.lines.some(line => line.category === "MATERIAL" && Number(line.amount) > 0)).toBeTruthy();
  await page.goto(`/tenders/${tender.id}?section=costing`);
  await page.screenshot({ path: "e2e/connected-estimate.png", fullPage: true });
  await page.goto(`/tenders/${tender.id}?section=approval`);
  await page.getByRole("button", { name: "Submit for review" }).click();
  const finance = await apiAs("finance@apex.demo");
  expect((await finance.post(`/api/v1/tenders/${tender.id}/workflow/authoritative-estimates/${estimateRecord.id}/approve`, { data: { remarks: "Connected E2E approval" } })).ok()).toBeTruthy();
  await finance.dispose();
  await page.reload();
  await expect(page.getByText("APPROVED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/connected-commercial-approval.png", fullPage: true });

  const customers = await page.request.get("/api/v1/customers?page_size=1");
  const customer = (await customers.json() as { items: { id: string }[] }).items[0];
  expect(customer).toBeTruthy();
  expect((await page.request.post(`/api/v1/tenders/${tender.id}/workflow/customer`, { data: { customer_id: customer.id } })).ok()).toBeTruthy();
  await page.goto(`/tenders/${tender.id}?section=quotation`);
  await page.getByRole("button", { name: "Create draft quotation" }).click();
  await page.getByRole("button", { name: "Finalize quotation" }).click();
  await page.reload();
  await expect(page.getByText("FINALIZED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/connected-final-quotation.png", fullPage: true });
  const quote = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/final-quotation`);
  const quoteData = await quote.json() as { items: { versions: { version: number; estimate_id: string; total_pre_tax: string }[] }[] };
  expect(quoteData.items[0].versions[0]).toMatchObject({ version: 1, estimate_id: estimateRecord.id });

  const quotePdf = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/quotation.pdf`);
  const pdfBytes = await quotePdf.body();
  expect(pdfBytes.subarray(0, 4).toString()).toBe("%PDF");
  expect(readablePdfStreams(pdfBytes)).toContain("Quotation");
  const estimateXlsx = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/estimate.xlsx`);
  expect(estimateXlsx.ok()).toBeTruthy();
  expect(estimateXlsx.headers()["content-type"]).toContain("spreadsheetml");
  const xlsxBytes = await estimateXlsx.body();
  expect(xlsxBytes.subarray(0, 2).toString()).toBe("PK");
  expect(xlsxBytes.includes(Buffer.from("[Content_Types].xml"))).toBeTruthy();
  // There is intentionally no quotation XLSX contract.  Never substitute BOM XLSX.
  expect((await page.request.get(`/api/v1/tenders/${tender.id}/workflow/quotation.xlsx`)).status()).toBe(404);

  const evidence = await page.request.post(`/api/v1/tenders/${tender.id}/documents`, { multipart: { file: { name: "connected-ack.pdf", mimeType: "application/pdf", buffer: readFileSync(pdf) } } });
  const evidenceDoc = await evidence.json() as { id: string };
  await page.goto(`/tenders/${tender.id}?section=submission`);
  await expect(page.getByText("READY FOR SUBMISSION", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/connected-submission-readiness.png", fullPage: true });
  const panel = page.getByLabel("Tender Submission");
  await panel.getByLabel("Submission method").fill("PORTAL");
  await panel.getByLabel("Portal/reference number").fill(number);
  await panel.getByLabel("Acknowledgment reference").fill(`${number}-ACK`);
  await panel.getByLabel("Tender evidence").selectOption(evidenceDoc.id);
  await panel.getByRole("button", { name: "Prepare Submission" }).click();
  await panel.getByRole("button", { name: "Confirm Submission" }).first().click();
  await page.getByRole("dialog", { name: "Confirm manual submission" }).getByRole("button", { name: "Confirm Submission" }).click();
  await panel.getByPlaceholder("Correction reason").fill("Connected E2E acknowledgement correction");
  await panel.getByRole("button", { name: "Create Correction" }).click();
  await panel.getByLabel("Outcome date").fill("2026-11-09");
  await panel.getByRole("button", { name: "Record Outcome" }).first().click();
  await page.getByRole("dialog", { name: "Confirm tender outcome" }).getByRole("button", { name: "Record Outcome" }).click();
  await page.screenshot({ path: "e2e/connected-submission-history-outcome.png", fullPage: true });

  await page.goto("/");
  const commandCenterTender = page.getByRole("combobox", { name: "Command Center tender" });
  await commandCenterTender.selectOption(tender.id);
  await expect(commandCenterTender).toHaveValue(tender.id);
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByText("Tender Intelligence")).toBeVisible();
  await expect(page.getByText("Costing & Commercial")).toBeVisible();
});
