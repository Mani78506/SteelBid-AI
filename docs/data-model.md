# SteelBid AI 2.0 — Data Model

PostgreSQL, SQLAlchemy 2.0, Alembic migrations. All PKs are `uuid`. All tenant-owned tables carry `organization_id` (FK `organizations.id`) and composite tenant indexes. Money = `Numeric(20,4)`, quantities = `Numeric(20,6)`. Timestamps are UTC (`timestamptz`). Soft-delete via `is_active` flags where relevant; hard-delete avoided on ledger/audit tables.

## Identity
- **organizations** — id, name, business_profiles (`text[]`: TRADER/DISTRIBUTOR/FABRICATOR/CONTRACTOR), currency_code (default INR), timezone, is_active, created_at/updated_at.
- **users** — id, email (unique), full_name, password_hash (argon2id), is_active, is_demo, created_at/updated_at.
- **memberships** — id, organization_id FK, user_id FK, role (ADMIN/SALES/PROCUREMENT/INVENTORY/FABRICATION/ESTIMATOR/FINANCE/VIEWER), unique(organization_id, user_id).
- **sessions** — id (uuid, also cookie token lookup via hashed token), user_id FK, active_organization_id FK (nullable), expires_at, created_at, last_seen_at, ip, user_agent. Token stored as SHA-256 hash.

## CRM
- **customers** — id, organization_id, code per org, name, category, gstin, credit_terms_days, currency, is_active. unique(org, code).
- **customer_contacts** — id, organization_id, customer_id FK, name, email, phone, designation.
- **customer_inquiries** — id, organization_id, customer_id FK, reference, source (MANUAL/UPLOAD/BOQ_IMPORT), status (NEW/QUOTED/WON/LOST/CANCELLED), received_at, required_by, notes. unique(org, reference).
- **inquiry_items** — id, organization_id, inquiry_id FK, material_id FK (nullable for unmapped), description, form, grade, specification (jsonb), quantity, unit, target_price.

## Sales
- **quotations** — id, organization_id, inquiry_id FK (nullable), customer_id FK, number, status (DRAFT/PENDING_APPROVAL/APPROVED/SENT/ACCEPTED/REJECTED/EXPIRED/CONVERTED), current_version_id, currency, target_margin (Numeric 8,6), valid_until, created_by. unique(org, number).
- **quotation_versions** — id, organization_id, quotation_id FK, version_no, status, subtotal, total_estimated_cost, total_selling_price, gross_margin_pct, cost_estimate_id FK (nullable), approved_by/approved_at, is_immutable. unique(quotation_id, version_no).
- **quotation_items** — id, organization_id, quotation_version_id FK, material_id FK, description, form, grade, quantity, unit, unit_cost, unit_price, line_estimated_cost, line_selling_price, available_qty (snapshot), shortage_qty (snapshot).
- **sales_orders** — id, organization_id, quotation_id FK, customer_id FK, number, status (CONFIRMED/IN_PRODUCTION/READY/DISPATCHED/CLOSED/CANCELLED), total_value, order_date, delivery_date. unique(org, number).
- **sales_order_items** — id, organization_id, sales_order_id FK, material_id FK, quantity, unit, unit_price, reserved_qty, delivered_qty.

## Materials
- **material_catalog** — global reference catalog (not tenant-owned): id, sku, name, form (PLATE/BEAM/CHANNEL/ANGLE/PIPE/RHS/SHS/COIL/SHEET/REBAR/CHEQUERED/ROUND_BAR), grade, standard, density, base_unit. Seeded globally.
- **organization_materials** — id, organization_id, catalog_id FK (nullable), sku, name, form, grade, standard, base_unit, density, specification (jsonb), is_active, low_stock_threshold. unique(org, sku).
- **material_specs** — id, organization_id, organization_material_id FK, dimension_type, dimensions (jsonb: thickness/width/length/section...), weight_per_meter.
- **unit_conversions** — id, organization_id (nullable = global), from_unit, to_unit, factor (Numeric 20,10).

## Market
- **price_sources** — id, organization_id (nullable = global), name, source_type (SYNTHETIC/MANUAL/PROVIDER), is_synthetic, provider_key.
- **price_observations** — id, organization_id (nullable = global), source_id FK, material_form, grade, region, dimension_note, price_per_unit, unit, currency, observed_on, is_synthetic. index (form, grade, region, observed_on).
- **price_scenarios** — id, organization_id, name, parameters (jsonb), results (jsonb), created_by, created_at.

## Procurement
- **suppliers** — id, organization_id, code, name, category, payment_terms_days, lead_time_days, rating, contact fields, material_capabilities (`text[]`), is_active. unique(org, code).
- **purchase_requests** — id, organization_id, number, status (DRAFT/RFQ_ISSUED/ORDERED/FULFILLED/CANCELLED), source_type (SHORTAGE/MANUAL), reference (sales_order/inquiry link as jsonb `context`), needed_by, created_by. unique(org, number). Idempotency: unique(org, idempotency_key) nullable.
- **purchase_request_items** — id, organization_id, purchase_request_id FK, material_id FK, quantity, unit, required_by.
- **rfqs** — id, organization_id, purchase_request_id FK, number, status, issued_on, valid_until.
- **supplier_quotes** — id, organization_id, rfq_id FK, supplier_id FK, material_id FK, quantity, unit, unit_price, currency (normalized to org currency at entry rate), freight_per_unit, duty_pct, tax_pct, tax_recoverable (bool), payment_terms_days, lead_time_days, valid_until, status.
- **purchase_orders** — id, organization_id, supplier_id FK, number, status (DRAFT/PENDING_APPROVAL/APPROVED/SENT/PARTIALLY_RECEIVED/RECEIVED/CANCELLED), total_value, expected_delivery, approved_by/at. unique(org, number). unique(org, idempotency_key) nullable.
- **purchase_order_items** — id, organization_id, purchase_order_id FK, material_id FK, quantity, unit, unit_price, received_qty.
- **goods_receipts** — id, organization_id, purchase_order_id FK, number, received_on, warehouse_id FK, status. Movement: creates RECEIPT inventory_movements + stock_lots in one transaction.

## Inventory
- **warehouses** — id, organization_id, code, name, location, is_active. unique(org, code).
- **storage_locations** — id, organization_id, warehouse_id FK, code, name.
- **stock_lots** — id, organization_id, material_id FK, warehouse_id FK, storage_location_id FK (nullable), lot_number, heat_number, quality_status (OK/QUARANTINED/REJECTED), on_hand_qty, reserved_qty, unit, unit_cost, source (jsonb: PO/GRN/SEED). CHECK on_hand>=0, reserved>=0, reserved<=on_hand. unique(org, material, warehouse, lot_number).
- **inventory_movements** — id, organization_id, material_id FK, warehouse_id FK, stock_lot_id FK, movement_type (RECEIPT/ISSUE/TRANSFER_OUT/TRANSFER_IN/ADJUSTMENT/RESERVE/UNRESERVE/CONSUME/SCRAP), quantity (signed), unit, balance_after_on_hand, reference (jsonb), idempotency_key, created_by, created_at.
- **reservations** — id, organization_id, stock_lot_id FK, material_id FK, warehouse_id FK, quantity CHECK >0, status (ACTIVE/CONSUMED/CANCELLED), context (jsonb: sales_order id, work_order id), created_by, created_at. unique(org, idempotency_key) nullable.
- **stock_transfers** — id, organization_id, stock_lot_id FK, from_warehouse_id FK, to_warehouse_id FK, quantity, status, created_by.

## Fabrication
- **bom_versions** — id, organization_id, product_name, bom_code, version_no, status (DRAFT/APPROVED/OBSOLETE), estimated_material_cost, estimated_total_cost, approved_by/at. unique(org, bom_code, version_no).
- **bom_items** — id, organization_id, bom_version_id FK, material_id FK, quantity, unit, theoretical_waste_pct, notes.
- **routings** — id, organization_id, bom_version_id FK, sequence, operation_type (CUTTING/WELDING/DRILLING/MACHINING/PAINTING/COATING/ASSEMBLY/INSPECTION), work_center, est_hours, rate_per_hour.
- **work_orders** — id, organization_id, bom_version_id FK, sales_order_id FK (nullable), number, status (PLANNED/MATERIAL_ALLOCATED/IN_PROGRESS/QC/COMPLETED/CANCELLED), planned_qty, produced_qty, start_date, due_date, actual_material_cost, actual_labour_cost. unique(org, number).
- **production_operations** — id, organization_id, work_order_id FK, routing_id FK, sequence, operation_type, status (PENDING/IN_PROGRESS/COMPLETED/SKIPPED), started_at, completed_at, actual_hours, operator.
- **material_allocations** — id, organization_id, work_order_id FK, stock_lot_id FK, material_id FK, allocated_qty, consumed_qty, status.
- **scrap_records** — id, organization_id, work_order_id FK, material_id FK, quantity, unit, reason, recorded_by.
- **quality_inspections** — id, organization_id, work_order_id FK, inspection_type, result (PASS/FAIL/CONDITIONAL), inspector, notes, inspected_at.

## Projects & Tenders
- **projects** — id, organization_id, code, name, customer_id FK (nullable), project_type (RAILWAY/BRIDGE/BUILDING/INDUSTRIAL/FABRICATION), location, status, estimated_value, start_date, end_date. unique(org, code).
- **tenders** — id, organization_id, project_id FK (nullable), number, title, customer, project_type, location, submission_deadline, estimated_value, currency, description, status (DRAFT/IN_REVIEW/ESTIMATING/BID_SUBMITTED/WON/LOST/CANCELLED). unique(org, number).
- **tender_documents** — id, organization_id, tender_id FK, file_name, storage_key, mime_type, size_bytes, status (UPLOADED/EXTRACTING/EXTRACTED/REVIEWED/FAILED), uploaded_by, uploaded_at.
- **boq_items** — id, organization_id, tender_document_id FK, tender_id FK, line_no, raw_description, form, grade, specification (jsonb), quantity, unit, material_id FK (nullable mapping), review_status (PENDING/CONFIRMED/REJECTED), source (MANUAL/AI), page_ref.
- **project_requirements** — id, organization_id, project_id FK, material_id FK, quantity, unit, required_by, source (BOQ/MANUAL).
- **extraction_evidence** — id, organization_id, document_id FK (tender_document), ai_job_id FK, page, cell_ref, field, raw_value, normalized_value (jsonb), confidence, review_status (PENDING/CONFIRMED/EDITED/REJECTED), reviewer_id, reviewed_at, warnings (jsonb).

## Logistics
- **dispatches** — id, organization_id, sales_order_id FK (nullable), number, status (PLANNED/PICKING/READY/DISPATCHED/DELIVERED/CANCELLED), warehouse_id FK, vehicle, transporter, dispatch_date, delivery_date. unique(org, number).
- **dispatch_items** — id, organization_id, dispatch_id FK, sales_order_item_id FK (nullable), stock_lot_id FK, material_id FK, quantity, unit.
- **shipments** — id, organization_id, dispatch_id FK, tracking_ref, status, shipped_at, delivered_at, notes.

## Finance
- **cost_estimates** — id, organization_id, context (jsonb: quotation_version/tender/work_order id), status (DRAFT/APPROVED), material_cost, fabrication_cost, labour_cost, freight_cost, installation_cost, subcontracting_cost, overhead_cost, contingency_pct, contingency_amount, total_cost, currency, created_by, version, parent_estimate_id (nullable).
- **cost_lines** — id, organization_id, cost_estimate_id FK, category, description, material_id FK (nullable), quantity, unit, unit_cost, amount, source (jsonb: price observation/supplier quote/inventory).
- **invoices** — id, organization_id, invoice_type (SALES/PURCHASE), number, counterparty (customer_id/supplier_id), issue_date, due_date, subtotal, tax_amount, total, currency, status (DRAFT/ISSUED/PARTIALLY_PAID/PAID/OVERDUE/CANCELLED). unique(org, invoice_type, number).
- **payments** — id, organization_id, invoice_id FK, amount, paid_on, method, reference.

## Governance
- **approvals** — id, organization_id, entity_type, entity_id, approval_type (QUOTATION/PURCHASE_ORDER/BID/ADJUSTMENT), requested_by, status (PENDING/APPROVED/REJECTED), decided_by, decided_at, comment.
- **audit_events** — id, organization_id, user_id, action, entity_type, entity_id, diff (jsonb before/after), request_id, created_at. Append-only.
- **notifications** — id, organization_id, user_id (nullable = org-wide), kind, title, body, link, is_read, created_at.
- **ai_jobs** — id, organization_id, job_type (TENDER_EXTRACTION/INQUIRY_EXTRACTION/BRIEFING/EXPLANATION), status (QUEUED/RUNNING/SUCCEEDED/FAILED), input (jsonb), output (jsonb), error, created_by, created_at, completed_at, idempotency_key.

## Key integrity rules
- Every movement that mutates stock is written in the same DB transaction as its `stock_lots` row lock update; `balance_after_on_hand` is recorded for auditability and tests.
- `available = on_hand_qty - reserved_qty` (quality OK lots only). Quarantined/rejected lots never enter availability.
- Cross-org linking is rejected at the service layer (e.g. inquiry → customer/material must share `organization_id`).
