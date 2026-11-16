import { expect, test } from "@playwright/test";

const org = { id: "org-1", name: "JAYRAJ STEEL PRIVATE LIMITED", business_profiles: [], currency_code: "INR", timezone: "Asia/Kolkata", is_demo: true };
const enhanced = {
  organization: { id: "org-1", name: "JAYRAJ STEEL PRIVATE LIMITED", profiles: [], currency: "INR" }, kpis: {}, priorities: [], recent_inquiries: [], procurement_shortages: [], price_observations: [], upcoming_dispatches: [], production_status: [], tender_deadlines: [], recent_activity: [],
  market_trends: [{ form: "CHANNEL", grade: "E250", region: "Hyderabad", price_basis: "EX_WORKS", latest_price: "55800", currency: "INR", unit: "MT", observed_on: "2026-11-10", change_30d_pct: "0.01", is_synthetic: false, freshness_days: 3, source: "Authorized market provider" }], market_comparisons: [], scenario_summary: { total_scenarios: 0, period_days: 30 }, new_tenders: [], tender_pipeline: { DRAFT: 1 }, tender_amendments: [], boq_review_status: { pending_review: 0 }, bom_readiness: [], tender_shortages: [{ tender_id: "t-1", bom_item_id: "bom-1", material_id: "m-1", required_qty: "10.25", eligible_qty: "5.125", allocated_qty: "2.125", shortage_qty: "3", unit: "MT", status: "SHORTAGE", reasons: [] }],
  inventory_breakdown: { unit: "MT", on_hand: "20", eligible: "15", reserved: "5", quality_held: "2", allocated: "2.125", available: "10", unit_totals: [{ unit: "MT", on_hand: "20", eligible: "15", reserved: "5", quality_held: "2", allocated: "2.125", available: "10" }, { unit: "SQM", on_hand: "40", eligible: "40", reserved: "4", quality_held: "0", allocated: "0", available: "36" }, { unit: "PCS", on_hand: "12", eligible: "12", reserved: "2", quality_held: "0", allocated: "0", available: "10" }] },
  atp_by_material: [], active_costing_quotes: [], margin_exposure: { total_pending_value: "0", at_risk_margin: null }, pricing_scenarios: { total_scenarios: 0, tender_related: null }, open_rfqs: { count: 1 }, pending_quotes: { count: 1 }, procurement_requirements: [{ tender_id: "t-1", bom_item_id: "bom-1", requirement_snapshot_id: "r-1", material_id: "m-1", material_name: "ISMC 150 Channel E250", unit: "MT", required_quantity: "10.25", eligible_allocated_quantity: "2.125", remaining_shortage_quantity: "3", compatible_offer_count: 1, expired_offer_count: 1, selected_offer_quantity: "5.125", unfulfilled_quantity: "3", status: "SHORTAGE", blockers: ["supplier offer needs selection"] }], tender_financials: [{ tender_id: "t-1", tender_number: "T-100", official_estimated_value: null, currency: "INR", estimate_status: "AUTHORITATIVE_AWAITING_COMMERCIAL_APPROVAL", estimate_id: "e-1", estimate_total: "123.45", commercial_approval_status: "PENDING", estimate_source: "AUTHORITATIVE_TENDER_V1" }], delivery_risks: [], approval_queue: [], price_alerts: { stale_observations: 0, stale_threshold_days: 14 },
};

async function mockCommon(page: import("@playwright/test").Page, enhancedStatus = 200) {
  let enhancedRequests = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api", "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/v1/auth/me") return json({ user: { id: "u-1", email: "admin@jayraj.demo", full_name: "Jayraj Admin", is_demo: true }, active_organization: org, role: "ADMIN", memberships: [{ role: "ADMIN", organization: org }] });
    if (path === "/v1/auth/organizations") return json([org]);
    if (path === "/v1/dashboard/enhanced") { enhancedRequests += 1; return json(enhancedStatus === 200 ? enhanced : { detail: "enhanced dashboard unavailable" }, enhancedStatus); }
    if (path === "/v1/market/intelligence/overview") return json({ cards: [{ material_form: "CHANNEL", grade: "E250", region: "Hyderabad", price_basis: "EX_WORKS", currency: "INR", unit: "MT", price_per_unit: "55800", observed_on: "2026-11-10", source: "Authorized market provider", source_id: "source-1", freshness_days: 3, is_synthetic: false, movement_30d: { percentage_change: "0.01" } }] });
    if (path === "/v1/market/intelligence/history") return json({ status: "insufficient_history", reason: "Insufficient comparable observations." });
    if (path === "/v1/market/intelligence/sources") return json({ sources: [{ name: "Authorized market provider", freshness_days: 3 }] });
    if (path === "/v1/market/intelligence/freshness") return json({ stale_after_days: 14, series: [] });
    if (path === "/v1/tenders") return json({ items: [{ id: "t-1", number: "T-100", title: "Metro Yard Steel Package" }], total: 1, page: 1, page_size: 100, pages: 1 });
    if (path === "/v1/dashboard/tender-context/t-1") return json({ status: "READY", coverage: { MT: { required: "10.25", available: "5.125", covered: "7.25", uncovered: "3", percent: "70.73" } } });
    if (path === "/v1/dashboard/tender-profitability/t-1") return json({ has_estimate: true, material_cost: "100", additional_costs: "23.45" });
    if (path === "/v1/notifications") return json({ items: [] });
    if (path === "/v1/ai/daily-briefing") return json({ generated_at: "2026-11-06T00:00:00Z", summary: "", items: [], grounded_in: [], note: "" });
    return json({});
  });
  return () => enhancedRequests;
}

test("Command Center keeps portfolio view unselected and renders unit-safe facts", async ({ page }) => {
  await mockCommon(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Command Center tender" })).toHaveValue("");
  await expect(page.getByText("Portfolio view does not substitute another tender’s estimate.")).toBeVisible();
  await expect(page.locator("b", { hasText: "MT" }).first()).toBeVisible();
  await expect(page.getByText("SQM stock position")).toBeVisible();
  await expect(page.getByText("PCS stock position")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Steel Market Intelligence" })).toBeVisible();
  await expect(page.getByText("Insufficient comparable observations.")).toBeVisible();
  await page.getByRole("button", { name: "90D" }).click();
  await expect(page.getByRole("button", { name: "90D" })).toBeVisible();
  await expect(page.getByText("No notifications are recorded for you.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommended Actions" })).toBeVisible();
  await page.screenshot({ path: "e2e/phase4c-market-inventory.png", fullPage: true });
  await page.getByRole("combobox", { name: "Command Center tender" }).selectOption("t-1");
  await expect(page.getByLabel("Selected tender context")).toContainText("Metro Yard Steel Package · T-100");
  await expect(page.getByText("Estimate state: AUTHORITATIVE AWAITING COMMERCIAL APPROVAL")).toBeVisible();
  await expect(page.getByText(/Procurement requirements:/)).toBeVisible();
  await expect(page.getByText(/Open shortage/).first()).toBeVisible();
  await page.screenshot({ path: "e2e/phase4c-selected-procurement-financials.png", fullPage: true });
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
  await page.screenshot({ path: "e2e/phase4d-tablet-command-center.png", fullPage: true });
});

test("Command Center shows enhanced-dashboard failure with retry instead of a fallback", async ({ page }) => {
  const enhancedRequests = await mockCommon(page, 503);
  await page.goto("/");
  await expect(page.getByLabel("Enhanced dashboard error")).toBeVisible();
  await expect(page.getByText("The enhanced dashboard could not be loaded. No fallback values are shown.")).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect.poll(enhancedRequests).toBeGreaterThan(1);
  await page.screenshot({ path: "e2e/phase4c-enhanced-dashboard-error.png", fullPage: true });
});
