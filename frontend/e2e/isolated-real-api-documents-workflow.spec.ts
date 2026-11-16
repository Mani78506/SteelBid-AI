import { expect, request, test } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const password = "SteelBid#Demo2026";
const pdfPath = path.resolve(import.meta.dirname, "../../backend/pytest-tmp/boq_demo.pdf");

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("[DEMO] Apex Steel Traders Pvt Ltd").first()).toBeVisible();
}

async function authenticatedApi(email: string) {
  const context = await request.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3100" });
  const response = await context.post("/api/v1/auth/login", { data: { email, password } });
  expect(response.ok()).toBeTruthy();
  return context;
}

test("isolated real API: uploaded PDF persists through extraction, review, snapshot, BOM, and inventory", async ({ page }) => {
  expect(existsSync(pdfPath), `Training PDF unavailable: ${pdfPath}`).toBeTruthy();
  await login(page);

  const number = `E2E-DOC-${Date.now()}`;
  const created = await page.request.post("/api/v1/tenders", {
    data: { number, title: "[SYNTHETIC E2E] PDF extraction workspace", project_type: "FABRICATION" },
  });
  expect(created.ok()).toBeTruthy();
  const tender = await created.json() as { id: string };

  await page.goto(`/tenders/${tender.id}?section=documents`);
  await page.locator('input[type="file"]').setInputFiles(pdfPath);
  const documents = page.getByLabel("Documents and extraction");
  await expect(documents.getByText("boq_demo.pdf")).toBeVisible();
  await expect(documents.getByText("UPLOADED", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e/isolated-real-documents-uploaded.png", fullPage: true });

  await documents.getByRole("button", { name: "Extract BOQ" }).click();
  await expect(page.getByText(/Extraction created \d+ pending review row/)).toBeVisible();
  await expect(documents.getByText("EXTRACTED", { exact: true })).toBeVisible();

  const persistedDocuments = await page.request.get(`/api/v1/tenders/${tender.id}/documents`);
  expect(persistedDocuments.ok()).toBeTruthy();
  const document = (await persistedDocuments.json() as { id: string; file_name: string; status: string }[]).find((item) => item.file_name === "boq_demo.pdf");
  expect(document).toMatchObject({ file_name: "boq_demo.pdf", status: "EXTRACTED" });

  await page.goto(`/tenders/${tender.id}?section=requirements`);
  const requirements = page.getByLabel("Material requirements and BOM");
  await expect(requirements.getByText("ISMB 300").first()).toBeVisible();
  await expect(requirements.getByText("AI · p.1").first()).toBeVisible();
  await expect(requirements.getByText("PENDING", { exact: true }).first()).toBeVisible();
  await expect(requirements.getByRole("button", { name: "Snapshot approved requirements" })).toBeDisabled();
  await expect(requirements.getByRole("button", { name: "Generate / update BOM" })).toBeDisabled();
  await page.screenshot({ path: "e2e/isolated-real-extraction-results.png", fullPage: true });

  const boqResponse = await page.request.get(`/api/v1/tenders/${tender.id}/boq`);
  expect(boqResponse.ok()).toBeTruthy();
  const rows = await boqResponse.json() as { id: string; raw_description: string; form: string | null; grade: string | null; specification: Record<string, string>; quantity: string; unit: string; material_id: string | null; review_status: string; page_ref: string | null }[];
  expect(rows.length).toBeGreaterThanOrEqual(3);
  expect(rows.every((row) => row.review_status === "PENDING" && row.page_ref === "p.1" && row.unit === "MT" && row.quantity)).toBeTruthy();
  expect(rows.some((row) => row.form === "BEAM" && row.grade === "E250")).toBeTruthy();
  expect(rows.some((row) => row.form === "PLATE" && row.grade === "E250")).toBeTruthy();
  expect(rows.some((row) => Object.keys(row.specification ?? {}).length > 0)).toBeTruthy();

  const evidence = await page.request.get(`/api/v1/tenders/${tender.id}/evidence`);
  expect(evidence.ok()).toBeTruthy();
  const evidenceRows = await evidence.json() as { document_id: string; page: number | null; raw_value: string }[];
  expect(evidenceRows.length).toBe(rows.length);
  expect(evidenceRows.every((row) => row.document_id === document!.id && row.page === 1 && row.raw_value)).toBeTruthy();

  const editable = rows.find((row) => row.material_id);
  expect(editable, "No extracted BOQ row was mapped to an Apex tenant material").toBeTruthy();
  const editableRow = requirements.locator("tbody tr").filter({ hasText: editable!.raw_description });
  await editableRow.getByLabel(`Quantity for ${editable!.raw_description}`).fill("39");
  await editableRow.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("BOQ review saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel(`Quantity for ${editable!.raw_description}`)).toHaveValue("39.000000");
  await expect(requirements.getByText("CONFIRMED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/isolated-real-boq-reviewed.png", fullPage: true });

  await requirements.getByRole("button", { name: "Snapshot approved requirements" }).click();
  await expect(page.getByText("Approved requirement snapshot created.")).toBeVisible();
  await requirements.getByRole("button", { name: "Generate / update BOM" }).click();
  await expect(page.getByText("Tender BOM generated from approved requirements.")).toBeVisible();

  const snapshots = await page.request.get(`/api/v1/tenders/${tender.id}/requirement-snapshots`);
  expect(snapshots.ok()).toBeTruthy();
  const snapshotRows = await snapshots.json() as { material_id: string; quantity: string; unit: string; form: string | null; grade: string | null }[];
  expect(snapshotRows.some((row) => row.material_id === editable!.material_id && row.quantity === "39.000000" && row.unit === "MT")).toBeTruthy();
  const workflow = await page.request.get(`/api/v1/tenders/${tender.id}/workflow`);
  expect(workflow.ok()).toBeTruthy();
  const workflowData = await workflow.json() as { bom_version_id: string | null; shortages: { material_id: string; required_quantity: string; unit: string }[] };
  expect(workflowData.bom_version_id).toBeTruthy();
  expect(workflowData.shortages.some((row) => row.material_id === editable!.material_id && row.required_quantity === "39.000000" && row.unit === "MT")).toBeTruthy();
  await page.screenshot({ path: "e2e/isolated-real-bom-generated.png", fullPage: true });

  await page.goto(`/tenders/${tender.id}?section=inventory`);
  const inventory = page.getByLabel("Tender inventory match");
  await expect(inventory).toContainText("39 MT");
  await expect(inventory).toContainText("MT");

  const metro = await authenticatedApi("admin@metro.demo");
  const crossTenant = await metro.get(`/api/v1/tenders/${tender.id}/documents`);
  expect(crossTenant.status()).toBe(404);
  await metro.dispose();
  const viewer = await authenticatedApi("viewer@apex.demo");
  const roleDenied = await viewer.post(`/api/v1/tenders/${tender.id}/documents`, {
    multipart: { file: { name: "role-check.pdf", mimeType: "application/pdf", buffer: readFileSync(pdfPath) } },
  });
  expect(roleDenied.status()).toBe(403);
  await viewer.dispose();
});
