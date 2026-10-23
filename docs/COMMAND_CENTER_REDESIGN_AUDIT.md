# SteelBid AI — Command Center Redesign Audit

**Date:** 2026-10-21
**Status:** Audit Complete
**Next:** Stage 1 — Backend API Enhancements

---

## Current Command Center Audit

### Existing Frontend Structure (CommandCenter.tsx)

**Layout:**
- **Header:** Organization name, profiles, user name, "New inquiry" and "Procurement" buttons
- **KPI Grid:** 8 cards (inventory valuation, open SOs, purchase commitments, pending quotes, avg margin, overdue receivables, at-risk orders, pending approvals)
- **Left Column (2/3 width):**
  - Today's priorities (order deadlines, low stock, open PRs)
  - Recent sales inquiries table
  - Procurement shortages card
  - Upcoming dispatches card
  - Production status (fabricator only)
  - Tender deadlines (contractor only)
- **Right Column (1/3 width):**
  - AI Daily Briefing
  - Steel price observations
  - Recent activity

**Data Sources:**
- All data from `/api/v1/dashboard/summary` endpoint
- AI briefing from `/api/v1/ai/daily-briefing`

### Backend Dashboard API (/api/v1/dashboard/summary)

**Available Data:**
```python
{
  organization: {id, name, profiles, currency},
  kpis: {
    inventory_valuation: {value, currency},
    open_sales_order_value: {value, count, currency},
    purchase_commitments: {value, count, currency},
    pending_quotations: {count},
    estimated_gross_margin: {value, basis},
    overdue_receivables: {value, count, currency},
    at_risk_orders: {count},
    pending_approvals: {count},
    material_count, warehouse_count, supplier_count, customer_count,
    quotation_status_distribution
  },
  priorities: [
    {severity, kind, text, link}  // order deadlines, low stock, open PRs
  ],
  recent_inquiries: [{id, reference, customer, status, received_at}],
  procurement_shortages: [{pr_id, pr_number, material, quantity, status, needed_by}],
  price_observations: [{form, grade, region, price, unit, observed_on, is_synthetic}],
  upcoming_dispatches: [{id, number, status, dispatch_date, transporter}],
  production_status: [{id, number, status, planned_qty, produced_qty}],
  tender_deadlines: [{id, number, title, deadline, status}],
  recent_activity: [{id, action, entity_type, created_at, user_id}]
}
```

**Gaps for New Requirements:**

| Requirement | Current Status | Gap |
|-------------|---------------|-----|
| **Steel Market Intelligence** | ✓ Latest price observations | ✗ Historical graphs, product/location filters, comparisons, forecast scenarios |
| **Tender Intelligence** | ✓ Tender deadlines | ✗ New relevant tenders, tender amendments, saved tender pipeline, direct analyze actions |
| **BOQ/BOM Intelligence** | ✗ Not present | ✗ Extracted requirements, BOQ review status, BOM approval status, material readiness indicators, tender-specific shortages |
| **Inventory Intelligence** | ✓ Procurement shortages | ✗ On-hand vs ATP breakdown, reserved/quality-held breakdown (combined not separate) |
| **Tender Costing** | ✗ Not present | ✗ Estimated material cost, supplier comparisons, margin exposure, pricing scenarios, prepare quotation action |
| **Procurement Intelligence** | ✓ Procurement shortages | ✗ Open RFQs, supplier quotations, delivery/cost risks |
| **AI Business Briefing** | ✓ AI Daily Briefing | ✗ Already implemented (good) |
| **Approvals & Notifications** | ✓ Pending approvals in KPI | ✗ Tender deadlines, material shortages, price alerts, approval actions (not in queue) |

---

## Available API Endpoints

### Market Intelligence (`/api/v1/market/*`)
- `GET /observations` — List with filters (form, grade, region, price_basis)
- `POST /observations` — Manual entry
- `POST /observations/import` — CSV import (Phase 2)
- `GET /trends` — Historical line chart with 30d/90d % change
- `GET /freshness-warnings` — Stale data warnings
- `POST /scenarios` — Price scenario analysis
- `GET /scenarios` — List scenarios

**Can provide:** Historical graphs, product/location filters, daily/monthly comparisons, forecast scenarios (via scenarios)

### Tenders (`/api/v1/tenders/*`)
- `GET /tenders` — List with filters (status, organization)
- `POST /tenders` — Create tender
- `GET /tenders/{id}` — Get tender details
- `PATCH /tenders/{id}` — Update tender
- `POST /tenders/{id}/upload` — Upload document
- `GET /tenders/{id}/boq/requirements-preview` — Extracted BOQ preview
- `GET /tenders/{id}/boq/items` — BOQ items for review

**Can provide:** New tenders (sorted by deadline), tender amendments (via update tracking), saved pipeline (via status filter), direct analyze actions (link to BOQ review)

### Fabrication/BOM (`/api/v1/fabrication/*`)
- `GET /boms` — List BOMs
- `POST /boms` — Create BOM
- `GET /work-orders` — List work orders
- `POST /work-orders` — Create work order

**Gap:** No explicit BOQ → BOM mapping API. Need to extract from tender BOQ items.

### Inventory (`/api/v1/inventory/*`)
- `GET /stock-lots` — List stock lots
- `GET /warehouses` — List warehouses
- `GET /availability/{material_id}` — Material availability breakdown
- `POST /movements` — Record movement
- `POST /reservations` — Reserve stock

**Can provide:** On-hand, available, reserved, quality-held breakdown (via lot filtering)

### Procurement (`/api/v1/procurement/*`)
- `GET /suppliers` — List suppliers
- `GET /purchase-requests` — List PRs
- `POST /purchase-requests` — Create PR
- `POST /procurement/shortage-request` — Auto-create PR from shortage
- `GET /supplier-quotes` — List supplier quotes
- `POST /supplier-quotes` — Add quote
- `GET /procurement/compare` — Landed-cost comparison
- `GET /purchase-orders` — List POs
- `POST /purchase-orders` — Create PO
- `POST /purchase-orders/{id}/approve` — Approve PO

**Can provide:** Open RFQs (via PR status), supplier quotations, purchase requirements, delivery/cost risks (via PO delivery dates)

### Quotations (`/api/v1/quotations/*`)
- `GET /quotations` — List quotations
- `POST /quotations` — Create quotation
- `GET /quotations/{id}` — Get quotation
- `POST /quotations/{id}/approve` — Approve quotation
- `GET /quotations/{id}/export` — Export quotation

**Can provide:** Pending quotations, margin exposure (via version margin), prepare quotation action (approve workflow)

---

## Recommended Implementation Plan

### Stage 1: Backend API Enhancements

**New Endpoint:** `GET /api/v1/dashboard/enhanced`

**Add to response:**
1. **Market Intelligence enhancements:**
   - `market_trends`: Pre-computed trends for top 3 products (BEAM, PLATE, COIL)
   - `market_comparisons`: 30d vs 90d price changes for key products
   - `scenario_summary`: Recent scenario results count

2. **Tender Intelligence enhancements:**
   - `new_tenders`: Top 5 tenders by deadline (within 30 days)
   - `tender_pipeline`: Pipeline counts by status (DRAFT, IN_REVIEW, ESTIMATING, BID_SUBMITTED)
   - `tender_amendments`: Recent tender modifications (last 7 days)

3. **BOQ/BOM Intelligence:**
   - `boq_review_status`: Count of tenders with BOQ pending review
   - `bom_readiness`: Material readiness for active work orders (based on inventory)
   - `tender_shortages`: Material shortages specifically linked to tender BOQs

4. **Inventory Intelligence (enhanced):**
   - `inventory_breakdown`: {on_hand, available, reserved, quality_held} summary
   - `atp_by_material`: Available-to-promise for top 5 materials

5. **Tender Costing Intelligence:**
   - `active_costing_quotes`: Quotations with pending approval (from tenders)
   - `margin_exposure`: Sum of margin at risk (pending quotes with price sensitivity)
   - `pricing_scenarios`: Recent scenario count related to tenders

6. **Procurement Intelligence (enhanced):**
   - `open_rfqs`: Count of RFQs issued
   - `pending_quotes`: Count of supplier quotes awaiting review
   - `delivery_risks`: POs with delivery within 3 days vs actual GRN status

7. **Approvals Queue:**
   - `approval_queue`: Consolidated list of pending approvals (quotations, POs, work orders)
   - `price_alerts`: Count of stale price observations (>14 days old)

**Files to modify:**
- `backend/app/api/dashboard.py` — Add new endpoint and computation logic
- `backend/app/schemas/ops.py` — Extend `DashboardSummary` or create new schema

### Stage 2: Frontend Layout Redesign

**New Layout Structure:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Header: Org name, profiles, user, tender action buttons           │
├─────────────────────────────────────────────────────────────────┤
│ KPI Bar (8 cards): Business health metrics                     │
├─────────────────────────────────────────────────────────────────┤
│ PRIMARY AREA (2 columns)                                        │
│ ┌──────────────────────────┬──────────────────────────────────┐ │
│ │ Steel Market Intelligence │ Tender Opportunities              │ │
│ │ - Latest prices           │ - New tenders (countdown)       │ │
│ │ - Historical chart        │ - Tender pipeline status        │ │
│ │ - Product/location filter │ - Recent amendments             │ │
│ │ - Price comparisons       │ - Direct analyze actions         │ │
│ └──────────────────────────┴──────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ SECONDARY AREA (3 columns)                                      │
│ ┌─────────────┬─────────────┬─────────────┐                      │
│ │ BOQ/BOM     │ Inventory    │ Procurement  │                      │
│ │ Intelligence│ Intelligence │ Intelligence │                      │
│ │ - BOQ review│ - On-hand/ATP│ - Open RFQs  │                      │
│ │ - BOM approval│ - Reserved   │ - Supplier    │                      │
│ │ - Material   │ - Quality    │   quotes     │                      │
│ │   readiness  │   held       │ - Delivery    │                      │
│ │ - Tender     │ - Tender     │   risks      │                      │
│ │   shortages  │   shortages  │              │                      │
│ └─────────────┴─────────────┴─────────────┘                      │
├─────────────────────────────────────────────────────────────────┤
│ BOTTOM AREA (2 columns)                                          │
│ ┌──────────────────────────┬──────────────────────────────────┐ │
│ │ Tender Costing           │ Approvals & Notifications       │ │
│ │ - Estimated cost         │ - Pending quotations           │ │
│ │ - Supplier comparisons   │ - Tender deadlines             │ │
│ │ - Margin exposure        │ - Material shortages           │ │
│ │ - Pricing scenarios      │ - Price alerts                 │ │
│ │ - Prepare quotation      │ - Approval actions              │ │
│ └──────────────────────────┴──────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ AI Briefing + Recent Activity (full width)                        │
└─────────────────────────────────────────────────────────────────┘
```

**Files to modify:**
- `frontend/src/pages/CommandCenter.tsx` — Complete layout restructure
- Create new components: `MarketIntelligenceCard.tsx`, `TenderOpportunitiesCard.tsx`, `BoqBomCard.tsx`, `InventoryIntelligenceCard.tsx`, `ProcurementIntelligenceCard.tsx`, `TenderCostingCard.tsx`, `ApprovalsCard.tsx`

### Stage 3: Interactive Widgets

**Features to add:**
1. **Market Trend Chart:** Embedded Recharts line chart in Market Intelligence card
2. **Tender Countdown:** Visual countdown timer for nearest deadline
3. **Pipeline Visualization:** Progress bar or funnel chart for tender pipeline
4. **Inventory Donut Chart:** On-hand vs ATP vs Reserved vs Quality-held
5. **Margin Exposure Bar:** Visual indicator of margin at risk

**Libraries:** Already using Recharts, Lucide React — no new dependencies needed

### Stage 4: Widget Visibility Configuration

**Implementation:**
- User preference stored in localStorage (simple version)
- Checkbox panel to toggle widget visibility
- Persist layout: Array of visible widget IDs
- Default: All widgets visible

**Files to create:**
- `frontend/src/hooks/useWidgetPreferences.ts` — Custom hook for widget visibility
- Add widget toggle button to Command Center header

### Stage 5: Tender Workflow Verification

**Test Path:**
1. Create tender → extract BOQ → review BOQ items
2. BOQ → create BOM → approve BOM
3. BOM → check inventory → identify shortages
4. Shortages → create PR → RFQ → supplier quotes
5. Quotes → landed-cost comparison → select supplier
6. Create quotation from cost estimate → approve quotation
7. Quotation → sales order → reserve stock

**Files to test:**
- `frontend/src/pages/Tenders.tsx`
- `frontend/src/pages/Fabrication.tsx`
- `frontend/src/pages/Inventory.tsx`
- `frontend/src/pages/Procurement.tsx`
- `frontend/src/pages/Quotations.tsx`
- `frontend/src/pages/SalesOrders.tsx`

### Stage 6: Testing & Documentation

**Tests to add:**
- Backend API test for `/dashboard/enhanced` endpoint
- Frontend component tests for new cards
- End-to-end Playwright test for full tender workflow
- Widget visibility toggle test

**Screenshots to capture:**
1. Initial load with all widgets
2. Market trend chart
3. Tender pipeline visualization
4. Inventory breakdown chart
5. Approval queue
6. Tender workflow complete (end-to-end)

**Documentation:**
- Update README.md with new Command Center features
- Document widget configuration
- Document tender workflow

---

## Current Blockers

**None identified.** All required APIs exist or can be enhanced without breaking changes. The redesign is purely additive and reorganizational.

---

## Estimated Effort

| Stage | Focus | Est. Time |
|-------|-------|-----------|
| Stage 1 | Backend API enhancements | 4 hours |
| Stage 2 | Frontend layout redesign | 6 hours |
| Stage 3 | Interactive widgets | 4 hours |
| Stage 4 | Widget visibility config | 2 hours |
| Stage 5 | Tender workflow verification | 3 hours |
| Stage 6 | Testing, screenshots, docs | 3 hours |
| **Total** | | **22 hours** |

---

## Recommendation

Proceed with **Stage 1: Backend API Enhancements** first, as all frontend widgets depend on having the right data structure from the API.
