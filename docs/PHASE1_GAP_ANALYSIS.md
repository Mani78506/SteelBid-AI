# SteelBid AI 2.0 — Phase 1 Gap Analysis Report

**Date:** 2026-10-19
**Status:** Complete
**Next Phase:** Phase 2 — Market Price Data Model & Market Watch UI

---

## Executive Summary

The existing SteelBid AI repository has a **strong foundation** for the Steel Price Intelligence & Procurement Decision Engine. Core models, APIs, and UI components are already in place for market observations, procurement workflows, inventory management, and the command center dashboard.

**Key Findings:**
- ✅ **60% of data models exist** (market, procurement, inventory, sales)
- ✅ **50% of backend APIs exist** (market, procurement, dashboard)
- ✅ **40% of frontend UI exists** (Market, Procurement, Command Center)
- ⚠️ **Missing:** Product coverage expansion, supplier comparison enhancement, profit simulator, alerts, demo scenario

**Estimated Effort:** 6 phases over ~40 hours of development + testing

---

## Module-by-Module Gap Analysis

### Module 1 — Steel Market Watch

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| HRC, CRC, TMT/rebar, structural, billet, scrap prices | ✅ Forms: BEAM, CHANNEL, PLATE, COIL, BAR, TMT, etc. | Add HRC, CRC, billet, scrap to form list | Medium |
| Filter by product, grade, size/spec, location, price basis, supplier, date | ✅ Partial: form, grade, region, date | Add size/spec, price basis, supplier filters | High |
| Historical line charts with change indicators | ✅ Trend charts with 30d/90d % change | Enhance for longer horizons, visual change indicators | Low |
| Source, observation date, currency, unit, tax treatment, freshness | ✅ Partial: source, date, currency, unit | Add tax treatment, price basis fields | Medium |
| Manual entry + CSV import | ✅ Manual entry via API | ❌ No CSV import | Medium |
| Provider adapters for licensed integrations | ✅ `source_type: SYNTHETIC/MANUAL/PROVIDER` | ❌ No actual provider adapters | Low (future) |
| Clearly labeled synthetic demo data | ✅ `is_synthetic` flag, UI labels | ✅ Already implemented | N/A |

**Action Items:**
1. Expand `FORMS` constant in frontend Market.tsx to include HRC, CRC, BILLET, SCRAP
2. Add `price_basis` (ex-works, delivered, etc.) and `dimension_note` fields to `PriceObservation` model
3. Add CSV import endpoint in `market.py` API
4. Enhance trend chart visual indicators (color-coded change badges)

---

### Module 2 — Supplier Quotation Comparison

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Create material purchase requirement | ✅ `PurchaseRequest` API exists | ✅ Already implemented | N/A |
| Select eligible suppliers | ✅ Supplier list with capabilities | ❌ No eligibility matching engine | High |
| Send/export RFQs | ✅ `RFQ` model exists | ❌ No send/export functionality | High |
| Record supplier quotations | ✅ `SupplierQuote` API exists | ✅ Already implemented | N/A |
| Compare price, freight, delivery, payment, quality, specs | ✅ `/procurement/compare` endpoint with landed cost | ❌ UI for comparison table missing | High |
| Calculate comparable landed costs | ✅ `landed_unit_cost` in `calc/finance.py` | ✅ Already implemented | N/A |
| Recommend options with transparent reasoning | ❌ No recommendation engine | ❌ Missing entirely | High |
| Convert approved quotation to PO | ✅ PO creation from quote possible | ❌ No direct convert workflow | Medium |
| Grade/size/basis/tax comparability validation | ❌ No comparability checks | ❌ Missing entirely | High |

**Action Items:**
1. Build Supplier Comparison UI page (`frontend/src/pages/SupplierComparison.tsx`)
2. Add eligibility matching engine in `backend/app/services/suppliers.py`
3. Add recommendation logic to `backend/app/calc/suppliers.py`
4. Add direct quote-to-PO conversion endpoint in `procurement.py`
5. Add comparability validation service (check grade, size, basis, tax before comparison)

---

### Module 3 — Profit & Price Simulator

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Interactive scenario calculator | ✅ `/market/scenarios` exists | ❌ Basic delta-only, not full profit sim | High |
| Inputs: material, quantity, inventory, valuation, purchase price, freight, handling, processing, duties, taxes, expenses, selling price, target margin | ❌ Only: material, qty, price delta | ❌ Missing most cost components | High |
| Outputs: eligible stock, shortage, landed cost, COGS, gross profit, margin %, break-even, required price for target margin, sensitivity | ❌ Only: base/scenario price, exposure delta | ❌ Missing profit calculations | High |
| Tax treatment: recoverable GST not auto-expensed | ✅ `tax_recoverable` field exists | ❌ Not used in scenario calc | Medium |
| Persist scenarios with version history | ✅ `PriceScenario` model exists | ❌ No versioning, immutable revisions | Medium |
| Show assumptions and formulas | ❌ No formula disclosure | ❌ Missing entirely | Medium |

**Action Items:**
1. Create new model `PricingScenario` with versioning (extend or replace `PriceScenario`)
2. Create `backend/app/calc/pricing.py` with full profit simulation logic
3. Create API endpoint `/pricing/simulate` in new `backend/app/api/pricing.py`
4. Create Profit Simulator UI page (`frontend/src/pages/ProfitSimulator.tsx`)
5. Add scenario version history and immutability

---

### Module 4 — Inventory & Procurement Connection

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Check eligible available stock on inquiry | ✅ `material_availability` service exists | ✅ Already implemented | N/A |
| Exclude reserved/unavailable stock | ✅ Reservation model exists | ✅ Already implemented | N/A |
| Identify shortages | ✅ `shortage_qty` in `calc/finance.py` | ✅ Already implemented | N/A |
| Suggest supplier RFQs for shortage | ❌ No auto-suggestion | ❌ Missing entirely | High |
| Calculate estimated procurement costs | ❌ No estimation from quotes | ❌ Missing entirely | High |
| Prepare quotation estimate | ✅ Quotation items have cost/price | ❌ No auto-population from quotes | Medium |
| Require human approval before commitments | ✅ Approval model exists | ❌ Not wired to quotation flow | High |
| Quotation → SO conversion with stock reservation | ✅ Quotation → SO possible | ❌ No auto-reservation on conversion | High |
| Create purchase requests for uncovered quantities | ✅ `shortage_request` endpoint exists | ✅ Already implemented | N/A |
| Never modify physical inventory from recommendation | ✅ No auto-modification | ✅ Safe by design | N/A |

**Action Items:**
1. Add RFQ suggestion service in `backend/app/services/procurement.py`
2. Add procurement cost estimation from best quotes in `calc/finance.py`
3. Wire approval workflow to quotation → SO conversion
4. Add auto-reservation logic on SO creation
5. Add quotation estimate auto-population from procurement cost estimates

---

### Module 5 — Owner's Business Command Center

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Stock value | ✅ KPI exists | ✅ Already implemented | N/A |
| Open sales orders | ✅ KPI exists | ✅ Already implemented | N/A |
| Open purchase requirements | ✅ KPI exists | ✅ Already implemented | N/A |
| Margin exposure | ❌ No margin exposure KPI | ❌ Missing entirely | High |
| Pending approvals | ✅ KPI exists | ✅ Already implemented | N/A |
| Overdue receivables | ✅ KPI exists | ✅ Already implemented | N/A |
| Price changes affecting open quotations | ❌ No price impact alerts | ❌ Missing entirely | High |
| Procurement risks | ❌ No procurement risk KPI | ❌ Missing entirely | Medium |
| Operational priorities | ✅ Priority list exists | ✅ Already implemented | N/A |
| Traceable data sources | ✅ Audit logs exist | ✅ Already implemented | N/A |
| Informative empty states | ✅ Partially implemented | ❌ Some pages need empty states | Low |

**Action Items:**
1. Add margin exposure KPI to dashboard (sum of margin on open SOs)
2. Add price impact alert service (price change vs open quotations)
3. Add procurement risk KPI (overdue POs, delayed RFQs)
4. Add empty states to pages that lack them

---

### Module 6 — Price Alerts

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Configure alerts (material, location, threshold, % movement, target margin, quote expiry, quotation validity) | ❌ No alert configuration | ❌ Missing entirely | High |
| Persistent alerts and notification history | ❌ No alert tables | ❌ Missing entirely | High |
| Scheduled background jobs for periodic checks | ❌ No Celery tasks for alerts | ❌ Missing entirely | High |
| Prevent duplicate alerts | ❌ No deduplication logic | ❌ Missing entirely | Medium |
| Distinguish market observations from AI forecasts | ✅ `is_synthetic` flag exists | ✅ Already implemented | N/A |

**Action Items:**
1. Create models: `PriceAlertRule`, `PriceAlertEvent` in `backend/app/models/market.py`
2. Create Celery task in `backend/app/worker.py` for periodic alert checks
3. Create API endpoints in `backend/app/api/market.py` for alert CRUD
4. Create Alert Configuration UI page (`frontend/src/pages/Alerts.tsx`)
5. Add deduplication logic (alert per rule per day max)

---

### Module 7 — Data Model

| Table | Current State | Gap | Priority |
|-------|---------------|-----|----------|
| `market_price_sources` | ✅ `PriceSource` exists | Add `price_basis` field | Medium |
| `market_price_observations` | ✅ `PriceObservation` exists | Add `price_basis`, `dimension_note` | Medium |
| `supplier_price_quotes` | ✅ `SupplierQuote` exists | Add `comparability_key` for validation | High |
| `purchase_requirements` | ✅ `PurchaseRequest` exists | ✅ Already implemented | N/A |
| `purchase_requirement_items` | ✅ `PurchaseRequestItem` exists | ✅ Already implemented | N/A |
| `landed_cost_estimates` | ❌ Does not exist | ❌ Missing entirely | High |
| `pricing_scenarios` | ✅ `PriceScenario` exists | Replace with versioned model | High |
| `pricing_scenario_versions` | ❌ Does not exist | ❌ Missing entirely | High |
| `price_alert_rules` | ❌ Does not exist | ❌ Missing entirely | High |
| `price_alert_events` | ❌ Does not exist | ❌ Missing entirely | High |
| `procurement_recommendations` | ❌ Does not exist | ❌ Missing entirely | High |
| `approval_records` | ✅ `Approval` exists | ✅ Already implemented | N/A |
| `audit_events` | ✅ `AuditEvent` exists | ✅ Already implemented | N/A |

**Action Items:**
1. Add migration to extend `PriceSource` and `PriceObservation` with new fields
2. Create `LandedCostEstimate` model
3. Create versioned `PricingScenario` and `PricingScenarioVersion` models
4. Create `PriceAlertRule` and `PriceAlertEvent` models
5. Create `ProcurementRecommendation` model
6. Add indexes for alert rule queries and scenario lookups

---

### Module 8 — UI/UX

| Component | Current State | Gap | Priority |
|-----------|---------------|-----|----------|
| Dark charcoal sidebar | ✅ Implemented | ✅ Already implemented | N/A |
| Clean light content area | ✅ Implemented | ✅ Already implemented | N/A |
| Steel-blue accents | ✅ Implemented | ✅ Already implemented | N/A |
| Compact KPI cards | ✅ Implemented | ✅ Already implemented | N/A |
| Interactive price charts | ✅ Recharts line charts | ✅ Already implemented | N/A |
| Supplier comparison tables | ❌ Does not exist | ❌ Missing entirely | High |
| Cost breakdown visualizations | ❌ Does not exist | ❌ Missing entirely | High |
| Scenario simulation controls | ✅ Basic scenario UI | ❌ Needs full profit sim UI | High |
| Approval workflows | ❌ Does not exist | ❌ Missing entirely | High |
| Responsive layouts | ✅ Implemented | ✅ Already implemented | N/A |
| Loading/empty/success/error states | ✅ Partially implemented | ❌ Some pages need states | Low |

**Action Items:**
1. Create `SupplierComparison.tsx` with comparison table and landed cost viz
2. Create `ProfitSimulator.tsx` with full cost breakdown and sensitivity analysis
3. Create `Alerts.tsx` for alert configuration and history
4. Add approval workflow modals to Quotations and Procurement pages
5. Add missing empty states to pages

---

### Module 9 — Security & Testing

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Existing authentication integration | ✅ Session-cookie auth | ✅ Already implemented | N/A |
| Organization-level data isolation | ✅ `OrgScopedMixin` | ✅ Already implemented | N/A |
| Role-based permissions | ✅ `require()` decorator | ✅ Already implemented | N/A |
| Server-side validation | ✅ Pydantic schemas | ✅ Already implemented | N/A |
| Decimal-safe calculations | ✅ `q_money`, `q_ratio` utilities | ✅ Already implemented | N/A |
| Transaction-safe stock reservations | ✅ DB transactions on reservation | ✅ Already implemented | N/A |
| Immutable financial scenario revisions | ❌ No immutability | ❌ Missing entirely | High |
| Audit logs | ✅ `AuditEvent` model | ✅ Already implemented | N/A |
| pytest unit/integration tests | ✅ 68 passing tests | ⚠️ Need new module tests | High |
| Playwright e2e tests | ✅ 5 passing tests | ⚠️ Need new flow tests | High |

**Test Cases to Add:**
1. 100 MT demand with 40 MT available stock → 60 MT shortage
2. Three comparable supplier quotations → ranked by landed cost
3. Different freight and payment terms → landed cost calculation
4. Price increase reducing gross margin → sensitivity analysis
5. Invalid grade/size comparison → validation error
6. Expired supplier quotation → excluded from comparison
7. Insufficient available stock → reservation blocked
8. Concurrent reservations → transaction isolation
9. Unauthorized cross-organization access → 403
10. Alert rule trigger → event created, no duplicate

**Action Items:**
1. Add immutability to `PricingScenarioVersion` (set `is_immutable` on approval)
2. Write pytest tests for pricing simulation, supplier comparison, alerts
3. Write Playwright tests for 100 MT demo flow, supplier comparison, approval workflows
4. Add concurrency test for stock reservations

---

### Module 10 — Demo Experience

| Requirement | Current State | Gap | Priority |
|-------------|---------------|-----|----------|
| Fictional steel company demo workspace | ✅ 4 demo orgs exist | ✅ Already implemented | N/A |
| 100 MT customer inquiry scenario | ✅ Can create inquiry | ⚠️ No guided demo flow | Medium |
| 40 MT available stock, 60 MT shortage | ✅ Seed data can be adjusted | ⚠️ Seed needs scenario alignment | Medium |
| Procurement team compares 3 supplier quotes | ✅ Comparison endpoint exists | ⚠️ UI missing | Medium |
| Sales team calculates estimated costs and margin | ❌ No cost estimate service | ❌ Missing entirely | Medium |
| Quotation generated and submitted for approval | ✅ Quotation exists | ⚠️ No approval workflow | Medium |
| SO reserves stock, creates PR for shortage | ✅ PR exists, no auto-reservation | ⚠️ Partial | Medium |
| Owner dashboard reflects commitments | ✅ Dashboard has KPIs | ⚠️ Missing margin exposure | Medium |
| Clearly labeled fictional data | ✅ `[DEMO]` prefixes | ✅ Already implemented | N/A |

**Action Items:**
1. Adjust seed data to create exact 100 MT / 40 MT / 60 MT scenario
2. Create 3 supplier quotes for the shortage material
3. Create guided demo flow in UI (optional "Demo Mode" tour)
4. Ensure dashboard reflects margin exposure after SO creation

---

## Technology Stack Assessment

| Component | Required | Current | Status |
|-----------|----------|---------|--------|
| React + Vite + TypeScript | ✅ | ✅ | OK |
| Tailwind CSS | ✅ | ✅ | OK |
| shadcn/ui | ✅ | ✅ (hand-rolled equivalent) | OK |
| Lucide React | ✅ | ✅ | OK |
| Framer Motion | ✅ | ✅ | OK |
| Recharts | ✅ | ✅ | OK |
| TanStack Query | ✅ | ✅ | OK |
| Python + FastAPI | ✅ | ✅ | OK |
| SQLAlchemy 2.0 | ✅ | ✅ | OK |
| PostgreSQL | ✅ | ✅ | OK |
| Alembic | ✅ | ✅ | OK |
| Pydantic v2 | ✅ | ✅ | OK |
| Redis | ✅ | ✅ | OK |
| Celery | ✅ | ✅ | OK |
| Decimal arithmetic | ✅ | ✅ | OK |

**Verdict:** All required technologies are already in use. No new dependencies needed.

---

## Phase Implementation Plan

### Phase 2: Market Price Data Model & Market Watch UI
**Goal:** Complete premium interactive market dashboard with expanded product coverage and CSV import.

**Tasks:**
1. Extend `PriceObservation` model with `price_basis` and `dimension_note`
2. Add CSV import endpoint in `market.py`
3. Expand frontend forms list (HRC, CRC, BILLET, SCRAP)
4. Add size/spec, price basis filters to Market.tsx
5. Enhance trend chart visual indicators
6. Write tests for CSV import and filters
7. Update seed data with new product types

**Estimated Time:** 6 hours

---

### Phase 3: Supplier Comparison & Landed-Cost Engine
**Goal:** Build supplier quotation comparison with landed-cost calculation and recommendation engine.

**Tasks:**
1. Build Supplier Comparison UI page
2. Add eligibility matching engine
3. Add recommendation logic to `calc/suppliers.py`
4. Add comparability validation service
5. Add direct quote-to-PO conversion endpoint
6. Write tests for comparison and recommendation
7. Add 3 supplier quotes to seed data

**Estimated Time:** 8 hours

---

### Phase 4: Profit Simulator & Pricing Scenarios
**Goal:** Build interactive profit and price simulator with version history.

**Tasks:**
1. Create versioned `PricingScenario` and `PricingScenarioVersion` models
2. Create `calc/pricing.py` with full profit simulation
3. Create `/pricing/simulate` API endpoint
4. Create Profit Simulator UI page
5. Add scenario version history and immutability
6. Write tests for simulation calculations
7. Add demo scenarios to seed data

**Estimated Time:** 8 hours

---

### Phase 5: Inventory, Inquiries, Quotations, Procurement Connection
**Goal:** Wire end-to-end flow from inquiry to SO with auto-reservation and PR creation.

**Tasks:**
1. Add RFQ suggestion service
2. Add procurement cost estimation from quotes
3. Wire approval workflow to quotation → SO conversion
4. Add auto-reservation logic on SO creation
5. Add quotation estimate auto-population
6. Write tests for end-to-end flow
7. Adjust seed data for 100 MT scenario

**Estimated Time:** 8 hours

---

### Phase 6: Alerts, Owner Dashboard, Testing, Hardening
**Goal:** Implement price alerts, enhance owner dashboard, comprehensive testing.

**Tasks:**
1. Create `PriceAlertRule` and `PriceAlertEvent` models
2. Create Celery task for periodic alert checks
3. Create alert API endpoints
4. Create Alert Configuration UI page
5. Add margin exposure KPI to dashboard
6. Add price impact alert service
7. Add procurement risk KPI
8. Write pytest tests for all new modules
9. Write Playwright tests for demo flow
10. Add immutability to scenario versions
11. Run full test suite and fix issues

**Estimated Time:** 10 hours

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Data model changes break existing migrations | Medium | High | Use Alembic revision system, test migrations locally |
| Profit simulation calculation errors | Low | High | Decimal arithmetic, extensive unit tests, audit trail |
| Alert job performance impact on DB | Medium | Medium | Batch processing, indexing, monitoring |
| UI complexity affects performance | Low | Medium | React memoization, query caching, lazy loading |
| Cross-organization data leakage | Low | Critical | Strict `OrgScopedMixin`, role-based tests, audit logs |

---

## Success Criteria

- ✅ All new modules have database migrations
- ✅ All new APIs have Pydantic schemas and validation
- ✅ All new UI pages have loading/empty/error states
- ✅ All calculations use Decimal arithmetic
- ✅ All financial scenarios are immutable after approval
- ✅ All stock reservations are transaction-safe
- ✅ All cross-organization access returns 403
- ✅ pytest suite passes (≥ 100 tests)
- ✅ Playwright suite passes (≥ 10 tests)
- ✅ 100 MT demo flow works end-to-end
- ✅ Deployment to Railway succeeds
- ✅ No production security vulnerabilities

---

## Conclusion

The SteelBid AI repository has a **solid foundation** for the Steel Price Intelligence & Procurement Decision Engine. Approximately **40-50% of the required functionality** already exists, particularly in data models, basic APIs, and core UI components.

The **highest-priority gaps** are:
1. Supplier comparison UI and recommendation engine
2. Profit simulator with full cost breakdown
3. Price alerts and scheduled background jobs
4. End-to-end inquiry → SO → PR workflow with auto-reservation
5. Margin exposure and procurement risk KPIs

With **focused implementation over 6 phases (~40 hours)**, the system can be upgraded to a production-ready decision-support platform for Indian steel businesses.

**Recommendation:** Proceed with Phase 2 immediately.
