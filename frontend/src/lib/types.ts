/** API response types — mirrors backend Pydantic schemas. */

export interface Org {
  id: string; name: string; business_profiles: string[];
  currency_code: string; timezone: string; is_demo: boolean;
}
export interface Me {
  user: { id: string; email: string; full_name: string; is_demo: boolean };
  active_organization: Org | null;
  role: string | null;
  memberships: { role: string; organization: Org }[];
}
export interface Material {
  id: string; sku: string; name: string; form: string; grade: string | null;
  standard: string | null; base_unit: string; density: string | null;
  specification: Record<string, unknown> | null; low_stock_threshold: string | null;
  is_active: boolean;
}
export interface Availability {
  material_id: string; sku: string; name: string;
  on_hand: string; reserved: string; available: string; quality_held: string;
  low_stock_threshold: string | null; is_low: boolean;
}
export interface Warehouse { id: string; code: string; name: string; location: string | null; is_active: boolean }
export interface StockLot {
  id: string; material_id: string; material_sku?: string; material_name?: string;
  warehouse_id: string; warehouse_name?: string; storage_location_id: string | null;
  lot_number: string; heat_number: string | null; quality_status: string;
  on_hand_qty: string; reserved_qty: string; available_qty: string; unit: string;
  unit_cost: string | null; created_at: string;
}
export interface Movement {
  id: string; movement_type: string; material_id: string; warehouse_id: string;
  stock_lot_id: string | null; quantity: string; unit: string;
  balance_after_on_hand: string | null; reference: string | null; created_at: string;
}
export interface Supplier {
  id: string; code: string; name: string; category: string | null;
  contact_name: string | null; email: string | null; phone: string | null; city: string | null;
  payment_terms_days: number | null; lead_time_days: number | null; rating: string | null;
  material_capabilities: Record<string, unknown> | string[] | null;
  is_active: boolean; is_demo: boolean;
}
export interface ComparisonItem {
  supplier_id: string; supplier_name: string; unit_price: string;
  landed_cost: string; lead_time_days: number | null; payment_terms_days: number | null;
  lead_time_ok: boolean; rank: number; premium_vs_best: string | number | null;
}
export interface Customer {
  id: string; code: string; name: string; category: string | null; gstin: string | null;
  credit_terms_days: number | null; currency: string; is_active: boolean; is_demo: boolean;
}
export interface Inquiry {
  id: string; customer_id: string; customer_name?: string; reference: string; status: string;
  source: string | null; notes: string | null; received_at: string;
  required_by: string | null; items: InquiryItem[];
}
export interface InquiryItem {
  id: string; material_id: string | null; material_name?: string | null;
  description: string; form: string | null; grade: string | null;
  specification: Record<string, unknown> | null;
  quantity: string; unit: string; target_price: string | null;
}
export interface QuotationVersion {
  id: string; quotation_id: string; version_no: number; status: string; is_immutable: boolean;
  subtotal: string; total_estimated_cost: string; total_selling_price: string;
  gross_margin_pct: string; approved_by: string | null; approved_at: string | null;
}
export interface QuotationLine {
  id: string; material_id: string | null; description: string; form: string | null;
  grade: string | null; quantity: string; unit: string;
  unit_cost: string; unit_price: string;
  line_estimated_cost: string; line_selling_price: string;
  available_qty: string | null; shortage_qty: string | null;
}
export interface Quotation {
  id: string; number: string; customer_id: string; customer_name?: string; inquiry_id: string | null;
  status: string; target_margin: string; currency: string; valid_until: string | null;
  created_at: string; versions: QuotationVersion[]; items: QuotationLine[];
}
export interface SalesOrder {
  id: string; number: string; customer_id: string; customer_name?: string; quotation_id: string | null;
  status: string; total_value: string; order_date: string | null; delivery_date: string | null;
  created_at: string; items: SalesOrderItem[];
}
export interface SalesOrderItem {
  id: string; material_id: string | null; description: string; quantity: string; unit: string;
  unit_price: string; reserved_qty: string | null; delivered_qty: string | null;
}
export interface Reservation {
  id: string; sales_order_item_id: string; lot_id: string; quantity: string;
  status: string; reference: string | null; created_at: string;
}
export interface PurchaseRequest {
  id: string; number: string; status: string; source_type: string | null;
  context: Record<string, string> | null; needed_by: string | null;
  created_at: string;
  items: { id: string; material_id: string; material_name?: string; quantity: string; unit: string; required_by?: string | null }[];
}
export interface PurchaseOrder {
  id: string; number: string; supplier_id: string; supplier_name?: string; purchase_request_id: string | null;
  status: string; total_value: string; expected_delivery: string | null; approved_at: string | null;
  created_at: string;
  items: { id: string; material_id: string; material_name?: string; quantity: string; unit: string; unit_price: string; received_qty: string | null }[];
}
export interface PriceObservation {
  id: string; material_id?: string | null; material_form: string; grade: string | null;
  region: string; price_per_unit: string; unit: string; currency?: string;
  source_name?: string; source?: string; observed_on?: string; observed_at?: string;
  is_synthetic: boolean;
}
export interface Bom {
  id: string; number: string; name: string; product_description: string | null;
  status: string; version_no: number; output_quantity: string; output_unit: string;
  total_estimated_cost: string; items: BomItem[];
}
export interface BomItem {
  id: string; material_id: string; material_name?: string; quantity: string; unit: string;
  unit_cost: string; line_cost: string; wastage_pct: string | null; availability: string | null;
}
export interface WorkOrder {
  id: string; number: string; bom_id: string | null; status: string;
  planned_start: string | null; planned_end: string | null; actual_cost: string | null;
  operations: { id: string; seq: number; operation: string; status: string; hours: string | null }[];
}
export interface Tender {
  id: string; number: string; title: string; customer_name: string | null; project_type: string | null;
  location: string | null; submission_deadline: string | null; estimated_value: string | null;
  currency: string; status: string; documents: TenderDocument[]; boq_items: BoqItem[];
}
export interface TenderDocument {
  id: string; file_name: string; status: string; uploaded_at: string; extraction?: ExtractionResult | null;
}
export interface ExtractionResult {
  id: string; document_id: string; status: string; warnings: string[];
  items: EvidenceItem[];
}
export interface EvidenceItem {
  id: string; field: string; raw_value: string; normalized_value: string | null;
  unit: string | null; page: number | null; confidence: number | null;
  review_status: string; warnings: string[];
}
export interface BoqItem {
  id: string; description: string; quantity: string; unit: string; material_id: string | null;
  form: string | null; grade: string | null; source: string | null;
}
export interface Project {
  id: string; number: string; name: string; customer_id: string | null; location: string | null;
  status: string; budget_value: string | null; start_date: string | null; end_date: string | null;
}
export interface Dispatch {
  id: string; number: string; sales_order_id: string | null; status: string;
  vehicle_no: string | null; driver: string | null; destination: string | null;
  dispatch_date: string | null; items: { id: string; material_id: string; quantity: string; unit: string }[];
}
export interface Invoice {
  id: string; number: string; direction: string; party_name: string; status: string;
  subtotal: string; tax: string; total: string; balance: string; due_date: string | null; issued_at: string;
}
export interface AuditEvent {
  id: string; actor_email: string | null; action: string; entity: string; entity_id: string | null;
  summary: string | null; payload: Record<string, unknown> | null; created_at: string;
}
export interface DashboardSummary {
  organization: { id: string; name: string; profiles: string[]; currency: string };
  kpis: Record<string, { value?: string; count?: number; currency?: string; basis?: string } | number | Record<string, number>>;
  priorities: { severity: string; kind: string; text: string; link: string | null }[];
  recent_inquiries: { id: string; reference: string; customer: string; status: string; received_at: string }[];
  procurement_shortages: { pr_id: string; pr_number: string; material: string; quantity: string; status: string; needed_by: string | null }[];
  price_observations: { form: string; grade: string | null; region: string; price: string; unit: string; observed_on: string; is_synthetic: boolean }[];
  upcoming_dispatches: { id: string; number: string; status: string; dispatch_date: string | null; transporter: string | null }[];
  production_status: { id: string; number: string; status: string; planned_qty: string; produced_qty: string }[];
  tender_deadlines: { id: string; number: string; title: string; deadline: string; status: string }[];
  recent_activity: { id: string; action: string; entity_type: string; created_at: string; user_id: string | null }[];
}

/** Server contract for /v1/dashboard/enhanced. Decimal values are strings. */
export interface EnhancedDashboardSummary extends DashboardSummary {
  market_trends: { form: string; grade: string | null; region: string; price_basis: string; latest_price: string; currency: string; unit: string; observed_on: string; change_30d_pct: string | null; is_synthetic: boolean; freshness_days: number; source: string }[];
  market_comparisons: { form: string; grade: string | null; price_30d: string; price_90d: string; change_pct: string }[];
  scenario_summary: { total_scenarios: number; period_days: number };
  new_tenders: { id: string; number: string; title: string; deadline: string; days_until: number; status: string }[];
  tender_pipeline: Record<string, number | string | null>;
  tender_amendments: { id: string; number: string; title: string; status: string; updated_at: string }[];
  boq_review_status: { pending_review: number };
  bom_readiness: { id: string; number: string; status: string; material_readiness: string | null }[];
  tender_shortages: { tender_id: string; material_id: string | null; required_qty: string | null; available_qty: string; shortage_qty: string }[];
  inventory_breakdown: { on_hand: string; available: string; reserved: string; quality_held: string; unit: string };
  atp_by_material: { material_id: string; name: string; available_atp: string }[];
  active_costing_quotes: { id: string; number: string; customer_id: string | null; total_selling: string | null; estimated_cost: string | null; gross_margin_pct: string | null }[];
  margin_exposure: { total_pending_value: string; at_risk_margin: string | null };
  pricing_scenarios: { total_scenarios: number; tender_related: number | null; label?: string };
  open_rfqs: { count: number }; pending_quotes: { count: number };
  delivery_risks: { id: string; number: string; expected_delivery: string; days_late: number; supplier_id: string }[];
  approval_queue: { type: string; id: string; number: string; value: string | null; created_at: string }[];
  price_alerts: { stale_observations: number; stale_threshold_days: number };
}
export interface Briefing {
  generated_at: string;
  summary: string;
  items: { kind: string; severity: string; text: string; link: string | null }[];
  grounded_in: { entity: string; id: string }[];
  note: string;
}
