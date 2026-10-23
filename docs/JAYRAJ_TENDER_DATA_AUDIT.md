# Jayraj tender data audit

Scope: the existing `JAYRAJ STEEL PRIVATE LIMITED` tenant only. No tenant or seed reset is required.

| Displayed value | Source | Notes |
| --- | --- | --- |
| Inventory on hand, reserved, quality-held | `stock_lots` | Portfolio inventory uses tenant-scoped lot aggregates. Eligible tender inventory additionally requires `quality_status = OK` and subtracts `reserved_qty`. |
| Tender requirements and BOQ | `boq_items` | Training BOQs are seeded records; their `source` and absent `tender_document_id` must not be presented as document extraction. |
| Approved requirements / BOM | `tender_requirement_snapshots`, `bom_versions`, `bom_items` | Tender coverage is unavailable until the workflow has a BOM version. |
| Tender coverage | `/v1/dashboard/tender-context/{tender_id}` | Per BOM material: `covered = min(required, eligible available)` and `uncovered = max(required - covered, 0)`. Totals are grouped by unit, never MT + SQM. |
| RFQs and supplier offers | `rfqs`, `supplier_quotes`, `tender_supplier_selections` | These are persisted commercial records, separate from inventory coverage. |
| Cost estimate and margin | `cost_estimates`, quotations | Cost detail is rendered only when a tender-linked estimate exists. |
| Workflow stage | `tender_documents`, `boq_items`, `tender_workflows` | A seeded BOQ without a document remains “Training BOQ available — source document not attached.” |
| Market references | `price_observations` | Market data is reference data; synthetic/simulated observations must retain their label and are not approved rates. |

Before the dashboard correction, the command center displayed a fixed 68% readiness message alongside a portfolio shortage. It was not connected to the selected tender. The tender-context endpoint uses the persisted approved BOM and eligible stock instead: a 231 MT requirement with 0 eligible MT reports 0% coverage and 231 MT uncovered; it cannot be “On track”.
