import { expect, test } from "@playwright/test";

const tender = { id: "tender-1", number: "TEST-SUB-001", title: "Mock submission tender", customer: "Mock Customer", project_type: "FABRICATION", location: null, submission_deadline: "2026-11-10T10:00:00Z", estimated_value: null, status: "DRAFT", documents_count: 1, boq_items_count: 0 };
const org = { id: "org-1", name: "JAYRAJ STEEL PRIVATE LIMITED", business_profiles: [], currency_code: "INR", timezone: "Asia/Kolkata", is_demo: true };

async function mockTenderWorkspace(page: import("@playwright/test").Page, options: { readiness?: string; blockers?: { code: string }[]; confirmed?: boolean; confirmDelayMs?: number; confirmErrorOnce?: boolean; inventoryMode?: "empty" | "error" | "delayed" } = {}) {
  const state = { readiness: options.readiness ?? "READY_FOR_SUBMISSION", blockers: options.blockers ?? [], confirmed: options.confirmed ?? false, confirmFailuresRemaining: options.confirmErrorOnce ? 1 : 0 };
  page.on("pageerror", error => console.log(`PAGE_ERROR: ${error.message}`));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()); const path = url.pathname.replace("/api", ""); const method = route.request().method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/v1/auth/me") return json({ user: { id: "u-1", email: "admin@jayraj.demo", full_name: "Jayraj Admin", is_demo: true }, active_organization: org, role: "ADMIN", memberships: [{ role: "ADMIN", organization: org }] });
    if (path === "/v1/auth/organizations") return json([org]);
    if (path === "/v1/tenders") return json({ items: [tender], total: 1, page: 1, page_size: 50, pages: 1 });
    if (path === `/v1/tenders/${tender.id}`) return json(tender);
    if (path === `/v1/tenders/${tender.id}/workspace/inventory-match`) { if (options.inventoryMode === "error") return json({ error: { message: "Inventory projection unavailable" } }, 500); if (options.inventoryMode === "delayed") await new Promise((resolve) => setTimeout(resolve, 700)); return json({ tender_id: tender.id, bom_version_id: "bom-1", items: options.inventoryMode === "empty" ? [] : [{ bom_item_id: "bom-1", requirement_snapshot_id: "snapshot-1", material_id: "material-1", material_name: "ISMB 200 E250", form: "BEAM", grade: "E250", specification: { standard: "IS 2062" }, required_quantity: "10.000000", unit: "MT", eligible_stock_quantity: "12.000000", reserved_quantity: "4.000000", quality_held_quantity: "2.000000", available_quantity: "8.000000", tender_allocated_quantity: "2.000000", shortage_quantity: "0.000000", matching_status: "READY", reasons: [] }, { bom_item_id: "bom-2", requirement_snapshot_id: "snapshot-2", material_id: "material-2", material_name: "Roof sheet", form: "SHEET", grade: "E250", specification: {}, required_quantity: "120.000000", unit: "SQM", eligible_stock_quantity: "40.000000", reserved_quantity: "0.000000", quality_held_quantity: "5.000000", available_quantity: "40.000000", tender_allocated_quantity: "0.000000", shortage_quantity: "80.000000", matching_status: "SHORTAGE", reasons: ["supplier sourcing required"] }] }); }
    if (path === `/v1/tenders/${tender.id}/documents` && method === "GET") return json([{ id: "doc-1", file_name: "same-tender-ack.pdf", mime_type: "application/pdf", size_bytes: 12, status: "UPLOADED", created_at: "2026-11-01T00:00:00Z" }]);
    if (path.endsWith("/documents/doc-1/extract")) return json({ job_id: "job-1", status: "SUCCEEDED", candidates: 1 }, 202);
    if (path === `/v1/tenders/${tender.id}/boq`) return json([{ id: "boq-1", raw_description: "ISMB 200 E250 10 MT", material_name: "ISMB 200 E250", material_id: "material-1", form: "BEAM", grade: "E250", specification: { standard: "IS 2062" }, quantity: "10", unit: "MT", review_status: "PENDING", source: "AI", page_ref: "p.1" }]);
    if (path === `/v1/tenders/${tender.id}/evidence`) return json([{ id: "evidence-1", document_id: "doc-1", page: 1, field: "boq_line", raw_value: "ISMB 200 E250 10 MT", confidence: "0.65", review_status: "PENDING", warnings: {} }]);
    if (path === `/v1/tenders/${tender.id}/workflow/procurement-requirements`) return json({ status: "NOT_CREATED", items: [], rfqs: [] });
    if (path === `/v1/tenders/${tender.id}/requirement-snapshots`) return json([]);
    if (path === `/v1/tenders/${tender.id}/supplier-selections/history`) return json([]);
    if (path.startsWith("/v1/suppliers")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    if (path === `/v1/tenders/${tender.id}/workflow/submission-readiness`) return json({ status: state.readiness, blockers: state.blockers, quotation_id: "quote-1", quotation_version_id: "version-1" });
    if (path === `/v1/tenders/${tender.id}/workflow/submissions` && method === "GET") return json(state.confirmed ? [{ id: "sub-1", status: "CONFIRMED", method: "PORTAL", portal_reference: "ACK-1", evidence_document_id: "doc-1", confirmed_at: "2026-11-02T00:00:00Z" }] : [{ id: "sub-1", status: "DRAFT", method: "PORTAL", portal_reference: "ACK-1", evidence_document_id: "doc-1" }]);
    if (path === `/v1/tenders/${tender.id}/workflow/submissions` && method === "POST") return json({ id: "sub-1", status: "DRAFT" }, 201);
    if (path.endsWith(`/v1/tenders/${tender.id}/workflow/submissions/sub-1/confirm`)) {
      if (options.confirmDelayMs) await new Promise(resolve => setTimeout(resolve, options.confirmDelayMs));
      if (state.confirmFailuresRemaining > 0) {
        state.confirmFailuresRemaining -= 1;
        return json({ error: { code: "EVIDENCE_REQUIRED", message: "Evidence must be verified before confirmation." } }, 422);
      }
      state.confirmed = true;
      return json({ id: "sub-1", status: "CONFIRMED" });
    }
    if (path.includes(`/v1/tenders/${tender.id}/workflow/submissions/sub-1`)) return json({ id: "sub-1", status: "DRAFT" });
    if (path === `/v1/tenders/${tender.id}/workflow`) return json({});
    if (path.startsWith("/v1/finance/cost-estimates")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    if (path.endsWith("/workflow/final-quotation")) return json({ tax_state: "NOT_RECORDED", items: [] });
    if (path.includes("/boq") || path.includes("/evidence") || path.includes("requirement-snapshots") || path.includes("supplier-selections") || path.includes("cost-estimates") || path.includes("authoritative-estimates") || path.includes("final-quotation") || path.includes("procurement-requirements") || path.includes("inventory-allocations") || path.includes("estimation-readiness")) return json([]);
    if (path.startsWith("/v1/customers") || path.startsWith("/v1/materials")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    return json({});
  });
}

test("full-page tender workspace renders tender-scoped inventory rows without unit aggregation", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}`);
  await expect(page.getByRole("heading", { name: tender.title })).toBeVisible();
  await expect(page.getByLabel("Tender workflow steps")).toContainText("Inventory Match");
  await expect(page.getByText("Tender Overview", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e/tender-workspace-overview.png", fullPage: true });
  await page.getByLabel("Tender workflow steps").getByRole("button", { name: /Inventory Match/ }).click();
  const table = page.getByLabel("Tender inventory match");
  await expect(table.getByText("ISMB 200 E250")).toBeVisible();
  await expect(table.getByText("Roof sheet")).toBeVisible();
  const beam = table.locator("tbody tr").filter({ hasText: "ISMB 200 E250" });
  const sheet = table.locator("tbody tr").filter({ hasText: "Roof sheet" });
  await expect(beam).toContainText("10 MT"); await expect(beam).toContainText("12 MT"); await expect(beam).toContainText("4 MT"); await expect(beam).toContainText("2 MT"); await expect(beam).toContainText("8 MT");
  await expect(sheet).toContainText("120 SQM"); await expect(sheet).toContainText("40 SQM"); await expect(sheet).toContainText("5 SQM"); await expect(sheet).toContainText("80 SQM");
  await page.screenshot({ path: "e2e/tender-workspace-inventory-match.png", fullPage: true });
});

test("inventory match provides loading, empty, and API-error states", async ({ page }) => {
  await mockTenderWorkspace(page, { inventoryMode: "delayed" }); await page.goto(`/tenders/${tender.id}?section=inventory`);
  await expect(page.locator(".animate-pulse").first()).toBeVisible(); await expect(page.getByText("ISMB 200 E250")).toBeVisible();
  await page.unroute("**/api/**"); await mockTenderWorkspace(page, { inventoryMode: "empty" }); await page.goto(`/tenders/${tender.id}?section=inventory`);
  await expect(page.getByText("No tender BOM is available yet.")).toBeVisible();
  await page.unroute("**/api/**"); await mockTenderWorkspace(page, { inventoryMode: "error" }); await page.goto(`/tenders/${tender.id}?section=inventory`);
  await expect(page.getByText("Inventory projection unavailable")).toBeVisible();
});

test("documents section presents persisted source metadata and allows explicit extraction", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}?section=documents`);
  const documents = page.getByLabel("Documents and extraction");
  await expect(documents.getByRole("heading", { name: "Documents & Extraction" })).toBeVisible();
  await expect(documents.getByText("same-tender-ack.pdf")).toBeVisible();
  await expect(documents.getByText("UPLOADED", { exact: true })).toBeVisible();
  await expect(documents.getByRole("button", { name: "Extract BOQ" })).toBeVisible();
  await expect(documents.getByText("Extracted values remain pending human review.")).toBeVisible();
  await page.screenshot({ path: "e2e/tender-workspace-documents.png", fullPage: true });
});

test("requirements section keeps extracted BOQ pending and prevents unapproved BOM generation", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}?section=requirements`);
  const requirements = page.getByLabel("Material requirements and BOM");
  await expect(requirements.getByRole("heading", { name: "Material Requirements — BOQ / BOM" })).toBeVisible();
  await expect(requirements.getByText("ISMB 200 E250 10 MT")).toBeVisible();
  await expect(requirements.getByText("AI · p.1")).toBeVisible();
  await expect(requirements.getByText("0.65")).toBeVisible();
  await expect(requirements.getByText("PENDING", { exact: true }).first()).toBeVisible();
  await expect(requirements.getByRole("button", { name: "Approve", exact: true })).toBeVisible();
  await expect(requirements.getByRole("button", { name: "Snapshot approved requirements" })).toBeDisabled();
  await expect(requirements.getByRole("button", { name: "Generate / update BOM" })).toBeDisabled();
  await page.screenshot({ path: "e2e/tender-workspace-requirements.png", fullPage: true });
});

test("procurement workspace shows shortage-driven empty and permission-safe states", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}?section=procurement`);
  const procurement = page.getByLabel("Tender procurement and supplier offers");
  await expect(procurement.getByText("Tender procurement requirements")).toBeVisible();
  await expect(procurement.getByText("ISMB 200 E250")).toBeVisible();
  await expect(procurement.getByText("No tender procurement request has been created.")).toBeVisible();
  await expect(procurement.getByText("No approved requirement snapshot is available for supplier comparison.")).toBeVisible();
  await expect(procurement.getByText("No supplier selections have been made for this tender.")).toBeVisible();
  await page.screenshot({ path: "e2e/tender-workspace-procurement.png", fullPage: true });
});

test("costing and commercial approval workspace show persisted-workflow empty states", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}?section=costing`);
  await expect(page.getByLabel("Tender costing and profitability").getByText("No authoritative estimate has been created.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save authoritative draft" })).toBeVisible();
  await page.goto(`/tenders/${tender.id}?section=approval`);
  await expect(page.getByLabel("Tender commercial approval").getByText("No authoritative estimate is available for review.")).toBeVisible();
  await page.screenshot({ path: "e2e/tender-workspace-costing.png", fullPage: true });
});

test("quotation and submission workspace expose backend readiness and draft lifecycle", async ({ page }) => {
  await mockTenderWorkspace(page);
  await page.goto(`/tenders/${tender.id}?section=quotation`);
  await expect(page.getByLabel("Tender quotation and downloads").getByText("No persisted quotation.")).toBeVisible();
  await page.goto(`/tenders/${tender.id}?section=submission`);
  const submission = page.getByLabel("Tender submission and outcome");
  await expect(submission.getByText("READY FOR SUBMISSION", { exact: true }).first()).toBeVisible();
  await expect(submission.getByText("Tender Submission", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e/tender-workspace-submission.png", fullPage: true });
});

test("renders ready submission controls and persists prepare/save/confirm actions", async ({ page }) => {
  await mockTenderWorkspace(page); const requests: { method: string; url: string; body: string }[] = [];
  page.on("request", request => { if (request.url().includes("/workflow/submissions")) requests.push({ method: request.method(), url: request.url(), body: request.postData() ?? "" }); });
  await page.goto(`/tenders?tender=${tender.id}`);
  await expect(page.getByText("Tender Submission", { exact: true })).toBeVisible();
  await expect(page.getByText("READY FOR SUBMISSION", { exact: true })).toBeVisible();
  await page.getByLabel("Submission method").fill("PORTAL");
  await page.getByLabel("Portal/reference number").fill("PORTAL-42");
  await page.getByLabel("Tender evidence").selectOption("doc-1");
  await expect(page.getByLabel("Tender evidence")).toHaveValue("doc-1");
  await page.getByRole("button", { name: "Prepare Submission" }).click();
  await expect(page.getByText("Manual submission draft saved")).toBeVisible();
  await page.getByRole("button", { name: "Save Draft" }).click();
  await expect(page.getByText("Submission draft updated")).toBeVisible();
  await page.getByRole("button", { name: "Confirm Submission" }).first().click();
  await expect(page.getByRole("dialog", { name: "Confirm manual submission" })).toBeVisible();
  await page.getByRole("dialog", { name: "Confirm manual submission" }).getByRole("button", { name: "Cancel" }).click();
  expect(requests.some(r => r.url.endsWith("/confirm"))).toBeFalsy();
  await page.getByRole("button", { name: "Confirm Submission" }).first().click();
  await page.getByRole("dialog", { name: "Confirm manual submission" }).getByRole("button", { name: "Confirm Submission" }).click();
  await expect.poll(() => requests.filter(r => r.method === "POST" || r.method === "PATCH").length).toBeGreaterThanOrEqual(3);
  expect(requests.some(r => r.method === "POST" && r.body.includes("quote-1"))).toBeTruthy();
  expect(requests.some(r => r.method === "PATCH" && r.body.includes("PORTAL-42"))).toBeTruthy();
  expect(requests.some(r => r.url.endsWith("/confirm"))).toBeTruthy();
});

test("renders blockers and keeps confirmation disabled until draft prerequisites exist", async ({ page }) => {
  await mockTenderWorkspace(page, { readiness: "NOT_READY", blockers: [{ code: "COMMERCIAL_APPROVAL_REQUIRED" }, { code: "REVALIDATION_REQUIRED" }] });
  await page.goto(`/tenders?tender=${tender.id}`);
  await expect(page.getByText("COMMERCIAL_APPROVAL_REQUIRED")).toBeVisible();
  await expect(page.getByText("REVALIDATION_REQUIRED")).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare Submission" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Confirm Submission" })).toBeDisabled();
});

test("confirmed history is read-only until correction reason and complete outcome are entered", async ({ page }) => {
  await mockTenderWorkspace(page, { confirmed: true });
  await page.goto(`/tenders?tender=${tender.id}`);
  await expect(page.getByText("CONFIRMED", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save Draft" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create Correction" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Record Outcome" })).toBeDisabled();
  await page.getByPlaceholder("Correction reason").fill("Correct evidence reference");
  await expect(page.getByRole("button", { name: "Create Correction" })).toBeEnabled();
  await page.getByLabel("Tender outcome").selectOption("LOST");
  await page.getByLabel("Outcome date").fill("2026-11-06");
  await expect(page.getByRole("button", { name: "Record Outcome" })).toBeEnabled();
});

test("outcome confirmation cancels without mutation and records only after explicit acceptance", async ({ page }) => {
  await mockTenderWorkspace(page, { confirmed: true });
  const outcomeRequests: string[] = [];
  page.on("request", request => {
    if (request.url().includes("/outcome")) outcomeRequests.push(request.url());
  });
  await page.goto(`/tenders?tender=${tender.id}`);
  await page.getByLabel("Outcome date").fill("2026-11-06");
  await page.getByRole("button", { name: "Record Outcome" }).first().click();
  await expect(page.getByRole("dialog", { name: "Confirm tender outcome" })).toBeVisible();
  await page.getByRole("dialog", { name: "Confirm tender outcome" }).getByRole("button", { name: "Cancel" }).click();
  expect(outcomeRequests).toHaveLength(0);
  await page.getByRole("button", { name: "Record Outcome" }).first().click();
  await page.getByRole("dialog", { name: "Confirm tender outcome" }).getByRole("button", { name: "Record Outcome" }).click();
  await expect.poll(() => outcomeRequests.length).toBe(1);
});

test("confirmation mutation disables controls and prevents duplicate requests until it completes", async ({ page }) => {
  await mockTenderWorkspace(page, { confirmDelayMs: 500 });
  const confirmations: string[] = [];
  page.on("request", request => { if (request.url().endsWith("/confirm")) confirmations.push(request.url()); });
  await page.goto(`/tenders?tender=${tender.id}`);
  await page.getByRole("button", { name: "Confirm Submission" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirm manual submission" });
  await dialog.getByRole("button", { name: "Confirm Submission" }).click();
  await expect(page.getByRole("button", { name: "Save Draft" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Confirm Submission" })).toBeDisabled();
  expect(confirmations).toHaveLength(1);
  await expect.poll(() => confirmations.length).toBe(1);
  await expect(page.getByRole("button", { name: "Save Draft" })).toBeEnabled();
});

test("backend confirmation error is surfaced and the user can cancel then retry", async ({ page }) => {
  await mockTenderWorkspace(page, { confirmErrorOnce: true });
  const confirmations: string[] = [];
  page.on("request", request => { if (request.url().endsWith("/confirm")) confirmations.push(request.url()); });
  await page.goto(`/tenders?tender=${tender.id}`);
  await page.getByRole("button", { name: "Confirm Submission" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirm manual submission" });
  await dialog.getByRole("button", { name: "Confirm Submission" }).click();
  await expect(page.getByText("Evidence must be verified before confirmation.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Confirm Submission" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Confirm Submission" }).first().click();
  await page.getByRole("dialog", { name: "Confirm manual submission" }).getByRole("button", { name: "Confirm Submission" }).click();
  await expect.poll(() => confirmations.length).toBe(2);
});
