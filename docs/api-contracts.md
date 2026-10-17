# SteelBid AI 2.0 — API Contracts

Base path: `/api/v1`. Interactive documentation (source of truth): `/api/docs` (Swagger UI) and `/api/openapi.json`.

## Conventions
- **Auth**: session cookie `steelbid_session` (HttpOnly, SameSite=Lax, Secure in prod). No bearer tokens, no localStorage.
- **Tenant scope**: the session's `active_organization_id` scopes every query. Switch org via `POST /api/v1/auth/switch-organization`.
- **Errors**: consistent envelope
  ```json
  { "error": { "code": "TENDER_NOT_FOUND", "message": "...", "details": {}, "request_id": "req_..." } }
  ```
  HTTP codes: 400 validation/business rule, 401 unauthenticated, 403 unauthorized role/membership, 404 not found (also used for cross-tenant guesses), 409 conflict/idempotency/state transition, 422 Pydantic validation.
- **Request IDs**: `X-Request-Id` response header on every request; echoed in error envelope and audit events.
- **Pagination**: `?page=1&page_size=20` (max 100) → `{ "items": [...], "total": n, "page": p, "page_size": s }`.
- **Filtering/sorting**: `?search=`, module filters (e.g. `?status=`, `?warehouse_id=`), `?sort=field` / `?sort=-field`.
- **Idempotency**: mutating workflow endpoints accept `Idempotency-Key` header; replays return the original result (409 `DUPLICATE_REQUEST` where a unique key collides with different payload).
- **Decimals**: serialized as strings to preserve precision.

## Endpoint groups
| Group | Prefix | Key endpoints |
|---|---|---|
| Auth | `/auth` | login, logout, me, refresh, organizations, switch-organization |
| Dashboard | `/dashboard` | summary (KPIs), briefing, activity, layouts per role |
| Customers | `/customers` | CRUD, contacts, inquiries, inquiry items |
| Quotations | `/quotations` | CRUD, versions, items, approve, convert-to-order, PDF export |
| Sales orders | `/sales-orders` | list, detail, status, reservations |
| Materials | `/materials` | org material CRUD, catalog, availability |
| Market | `/market` | price observations, trends, scenario analysis |
| Suppliers | `/suppliers` | CRUD, capability tags |
| Procurement | `/procurement` | purchase-requests, rfqs, supplier-quotes, compare, purchase-orders, approvals, goods-receipts |
| Inventory | `/inventory` | warehouses, storage locations, stock-lots, receipts, issues, adjustments, transfers, reservations, movements, valuation |
| Fabrication | `/fabrication` | boms, routings, work-orders, operations, allocations, scrap, inspections |
| Projects/Tenders | `/projects`, `/tenders` | CRUD, documents upload, extraction, boq-items review, requirements, cost estimate |
| Logistics | `/logistics` | dispatches, dispatch items, shipments |
| Finance | `/finance` | cost-estimates, invoices, payments, receivables/payables, valuation, profitability |
| AI | `/ai` | daily-briefing, explain shortage/supplier/price-risk, copilot query, jobs |
| Audit | `/audit` | events list (admin) |
| System | `/health` | liveness, readiness (DB ping) |

## Status flows (enforced server-side)
- Quotation: DRAFT → PENDING_APPROVAL → APPROVED → SENT → ACCEPTED → CONVERTED (also REJECTED/EXPIRED)
- Sales order: CONFIRMED → IN_PRODUCTION → READY → DISPATCHED → CLOSED (CANCELLED allowed until DISPATCHED)
- Purchase request: DRAFT → RFQ_ISSUED → ORDERED → FULFILLED (CANCELLED)
- Purchase order: DRAFT → PENDING_APPROVAL → APPROVED → SENT → PARTIALLY_RECEIVED → RECEIVED
- Work order: PLANNED → MATERIAL_ALLOCATED → IN_PROGRESS → QC → COMPLETED
- Tender: DRAFT → IN_REVIEW → ESTIMATING → BID_SUBMITTED → WON/LOST
