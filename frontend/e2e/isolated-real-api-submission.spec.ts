import { expect, test } from "@playwright/test";

const password = "SteelBid#Demo2026";
const tenderNumber = "E2E-SUB-001";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("admin@apex.demo");
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("[DEMO] Apex Steel Traders Pvt Ltd").first()).toBeVisible();
}

test("isolated real API: approved tender through submission, correction, and WON", async ({ page }) => {
  await login(page);
  const tenders = await page.request.get("/api/v1/tenders?page_size=100");
  expect(tenders.ok()).toBeTruthy();
  const tender = (await tenders.json()).items.find((item: { number: string }) => item.number === tenderNumber);
  expect(tender).toBeTruthy();

  await page.goto(`/tenders?tender=${tender.id}`);
  await expect(page.getByRole("dialog").getByRole("heading", { name: "[SYNTHETIC E2E] Approved Warehouse Steel Package" })).toBeVisible();
  await expect(page.getByText("ISMB 200 E250 synthetic E2E beam").first()).toBeVisible();
  await expect(page.getByText("Authoritative cost readiness")).toBeVisible();
  await expect(page.getByText("Final quotation", { exact: true })).toBeVisible();
  await expect(page.getByText("Tender Submission", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Tender workflow steps")).toContainText("BOQ Review");
  await expect(page.getByLabel("Tender workflow steps")).toContainText("BOM Generation");
  await expect(page.getByLabel("Tender workflow steps")).toContainText("Inventory Analysis");
  await expect(page.getByLabel("Tender workflow steps")).toContainText("Commercial Approval");
  await expect(page.getByLabel("Tender workflow steps")).toContainText("Quotation");
  await expect(page.getByLabel("Tender workflow steps")).toContainText("Submission Tracking");
  await expect(page.getByText("READY FOR SUBMISSION", { exact: true })).toBeVisible();

  await page.getByLabel("Submission method").fill("PORTAL");
  await page.getByLabel("Portal/reference number").fill("E2E-PORTAL-001");
  await page.getByLabel("Acknowledgment reference").fill("E2E-ACK-001");
  await page.getByLabel("Tender evidence").selectOption({ label: "synthetic-e2e-portal-ack.pdf" });
  await page.getByRole("button", { name: "Prepare Submission" }).click();
  await expect(page.getByRole("button", { name: "Save Draft" })).toBeVisible();
  await page.getByRole("button", { name: "Save Draft" }).click();
  await expect(page.getByText("Submission draft updated")).toBeVisible();
  await page.getByRole("button", { name: "Confirm Submission" }).first().click();
  await page.getByRole("dialog", { name: "Confirm manual submission" }).getByRole("button", { name: "Confirm Submission" }).click();
  await expect(page.getByText("CONFIRMED", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Confirm manual submission" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save Draft" })).toHaveCount(0);

  await page.getByPlaceholder("Correction reason").fill("Correct isolated E2E acknowledgement");
  await page.getByRole("button", { name: "Create Correction" }).click();
  await expect(page.getByText("Correction draft created")).toBeVisible();

  await page.getByLabel("Tender outcome").selectOption("WON");
  await page.getByLabel("Outcome date").fill("2026-11-06");
  await page.getByLabel("Outcome reference").fill("E2E-AWARD-001");
  await page.getByLabel("Outcome remarks").fill("Synthetic award for isolated browser verification");
  await page.getByLabel("Award value").fill("600000");
  await page.getByLabel("Award currency").fill("INR");
  await page.getByRole("button", { name: "Record Outcome" }).click();
  await page.getByRole("dialog", { name: "Confirm tender outcome" }).getByRole("button", { name: "Record Outcome" }).click();
  await expect(page.getByText("Tender outcome recorded")).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Confirm tender outcome" })).toHaveCount(0);

  const detail = await page.request.get(`/api/v1/tenders/${tender.id}`);
  expect(detail.ok()).toBeTruthy();
  expect((await detail.json()).status).toBe("WON");
  const history = await page.request.get(`/api/v1/tenders/${tender.id}/workflow/submissions`);
  const rows = await history.json();
  expect(rows.filter((row: { status: string }) => row.status === "CONFIRMED")).toHaveLength(1);
  expect(rows.some((row: { status: string }) => row.status === "DRAFT")).toBeTruthy();

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByText("Submission pipeline")).toBeVisible();
  await expect(page.getByText(/Confirmed: [1-9]/)).toBeVisible();
  await expect(page.getByText(/Needs attention: [1-9]/)).toBeVisible();
  await expect(page.getByText(/WON: [1-9]/)).toBeVisible();
});
