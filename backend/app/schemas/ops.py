"""Finance, logistics, dashboard, AI schemas."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DecimalOrNone, DecimalStr, OrmModel


# ---------- Cost estimates ----------
class CostLineIn(BaseModel):
    category: str
    description: str = Field(min_length=1, max_length=500)
    material_id: UUID | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_cost: Decimal | None = None
    amount: Decimal | None = None
    source: dict = {}


class CostEstimateIn(BaseModel):
    tender_id: UUID | None = None
    context: dict = {}
    overhead_cost: Decimal = Decimal("0")
    contingency_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=1)
    lines: list[CostLineIn] = []


class CostLineOut(OrmModel):
    id: UUID
    category: str
    description: str
    material_id: UUID | None
    quantity: DecimalOrNone
    unit: str | None
    unit_cost: DecimalOrNone
    amount: DecimalStr
    source: dict


class CostEstimateOut(OrmModel):
    id: UUID
    tender_id: UUID | None = None
    context: dict
    status: str
    version: int
    material_cost: DecimalStr
    fabrication_cost: DecimalStr
    labour_cost: DecimalStr
    freight_cost: DecimalStr
    installation_cost: DecimalStr
    subcontracting_cost: DecimalStr
    overhead_cost: DecimalStr
    contingency_pct: DecimalStr
    contingency_amount: DecimalStr
    total_cost: DecimalStr
    currency: str
    created_at: datetime
    lines: list[CostLineOut] = []


# ---------- Invoices ----------
class InvoiceIn(BaseModel):
    invoice_type: str = Field(pattern="^(SALES|PURCHASE)$")
    number: str = Field(min_length=1, max_length=64)
    customer_id: UUID | None = None
    supplier_id: UUID | None = None
    sales_order_id: UUID | None = None
    purchase_order_id: UUID | None = None
    issue_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)


class InvoiceOut(OrmModel):
    id: UUID
    invoice_type: str
    number: str
    customer_id: UUID | None
    supplier_id: UUID | None
    issue_date: date
    due_date: date | None
    subtotal: DecimalStr
    tax_amount: DecimalStr
    total: DecimalStr
    currency: str
    status: str
    paid_amount: DecimalStr | None = None


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date | None = None
    method: str | None = None
    reference: str | None = None


# ---------- Logistics ----------
class DispatchIn(BaseModel):
    sales_order_id: UUID | None = None
    warehouse_id: UUID
    vehicle: str | None = None
    transporter: str | None = None
    dispatch_date: date | None = None
    items: list["DispatchItemIn"] = []


class DispatchItemIn(BaseModel):
    sales_order_item_id: UUID | None = None
    stock_lot_id: UUID | None = None
    material_id: UUID
    quantity: Decimal = Field(gt=0)
    unit: str = "MT"


class DispatchOut(OrmModel):
    id: UUID
    sales_order_id: UUID | None
    warehouse_id: UUID
    number: str
    status: str
    vehicle: str | None
    transporter: str | None
    dispatch_date: date | None
    delivery_date: date | None
    created_at: datetime
    items: list[dict] = []


# ---------- Dashboard ----------
class DashboardSummary(BaseModel):
    organization: dict
    kpis: dict
    priorities: list[dict]
    recent_inquiries: list[dict]
    procurement_shortages: list[dict]
    price_observations: list[dict]
    upcoming_dispatches: list[dict]
    production_status: list[dict]
    tender_deadlines: list[dict]
    recent_activity: list[dict]


class EnhancedDashboardSummary(BaseModel):
    organization: dict
    kpis: dict
    priorities: list[dict]
    recent_inquiries: list[dict]
    procurement_shortages: list[dict]
    price_observations: list[dict]
    upcoming_dispatches: list[dict]
    production_status: list[dict]
    tender_deadlines: list[dict]
    recent_activity: list[dict]
    # NEW: Market Intelligence enhancements
    market_trends: list[dict]  # Comparable latest price series with provenance and freshness
    market_comparisons: list[dict]  # 30d vs 90d price changes for key products
    scenario_summary: dict  # Recent scenario results count
    # NEW: Tender Intelligence enhancements
    new_tenders: list[dict]  # Top 5 tenders by deadline (within 30 days)
    tender_pipeline: dict  # Pipeline counts by status
    tender_amendments: list[dict]  # Recent tender modifications (last 7 days)
    # NEW: BOQ/BOM Intelligence
    boq_review_status: dict  # Count of tenders with BOQ pending review
    bom_readiness: list[dict]  # Material readiness for active work orders
    tender_shortages: list[dict]  # Material shortages linked to tender BOQs
    # NEW: Inventory Intelligence (enhanced)
    inventory_breakdown: dict  # {on_hand, available, reserved, quality_held}
    atp_by_material: list[dict]  # Available-to-promise for top 5 materials
    # NEW: Tender Costing Intelligence
    active_costing_quotes: list[dict]  # Quotations with pending approval (from tenders)
    margin_exposure: dict  # Sum of margin at risk
    pricing_scenarios: dict  # Recent scenario count related to tenders
    # NEW: Procurement Intelligence (enhanced)
    open_rfqs: dict  # Count of RFQs issued
    pending_quotes: dict  # Count of supplier quotes awaiting review
    delivery_risks: list[dict]  # POs with delivery within 3 days vs actual GRN status
    # NEW: Approvals Queue
    approval_queue: list[dict]  # Consolidated list of pending approvals
    price_alerts: dict  # Count of stale price observations (>14 days old)


class BriefingOut(BaseModel):
    generated_at: datetime
    items: list[dict]
    summary: str
    grounded_in: list[dict]


# ---------- AI ----------
class ExplainIn(BaseModel):
    topic: str = Field(pattern="^(shortage|supplier_comparison|price_risk)$")
    entity: dict = {}


class CopilotIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    project_id: UUID | None = None


class AIJobOut(OrmModel):
    id: UUID
    job_type: str
    status: str
    input: dict
    output: dict
    error: str | None
    created_at: datetime
    completed_at: datetime | None
