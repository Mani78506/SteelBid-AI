"""Deterministic, idempotent demo seed.

Four FICTIONAL companies with consistent cross-module records. All demo records carry
`is_demo=True` where the column exists, and all price observations are labeled synthetic.
Design: fixed UUIDs (uuid5 over stable names), lookup-before-insert on every unique key,
so re-running is always safe. NEVER runs automatically in production — must be invoked
explicitly (`python -m app.seed.run`) and refuses when DEMO_MODE=false.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import hash_password
from app.models.crm import Customer, CustomerContact, CustomerInquiry, InquiryItem
from app.models.fabrication import (BOMItem, BOMVersion, MaterialAllocation,
                                    ProductionOperation, QualityInspection, Routing, WorkOrder)
from app.models.identity import Membership, Organization, User
from app.models.inventory import InventoryMovement, Reservation, StockLot, Warehouse
from app.models.market import PriceObservation, PriceSource
from app.models.materials import MaterialCatalog, OrganizationMaterial
from app.models.ops import (Approval, CostEstimate, CostLine, Dispatch, DispatchItem, Invoice,
                            Notification, Payment)
from app.models.procurement import (PurchaseOrder, PurchaseOrderItem, PurchaseRequest,
                                    PurchaseRequestItem, RFQ, Supplier, SupplierQuote)
from app.models.projects import BOQItem, Project, Tender, TenderRequirementSnapshot, TenderSupplierSelection
from app.models.sales import Quotation, QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem

NS = uuid.UUID("5b1d4a6a-1111-4f4f-8f8f-00000000000a")
NOW = datetime.now(timezone.utc)
TODAY = date.today()


def uid(name: str) -> uuid.UUID:
    return uuid.uuid5(NS, name)


def get_or_create(db: Session, model, defaults: dict | None = None, **lookup):
    obj = db.scalar(select(model).filter_by(**lookup))
    if obj is not None:
        return obj, False
    obj = model(**lookup, **(defaults or {}))
    db.add(obj)
    db.flush()
    return obj, True


CATALOG = [
    ("MS-PLT-E250-10", "MS Plate 10mm E250", "PLATE", "E250", "IS 2062", "7.85", "MT"),
    ("MS-PLT-E250-20", "MS Plate 20mm E250", "PLATE", "E250", "IS 2062", "7.85", "MT"),
    ("ISMB-200-E250", "ISMB 200 Beam E250", "BEAM", "E250", "IS 2062", "7.85", "MT"),
    ("ISMB-300-E250", "ISMB 300 Beam E250", "BEAM", "E250", "IS 2062", "7.85", "MT"),
    ("ISMC-150-E250", "ISMC 150 Channel E250", "CHANNEL", "E250", "IS 2062", "7.85", "MT"),
    ("ISA-50505-E250", "ISA 50x50x5 Angle E250", "ANGLE", "E250", "IS 2062", "7.85", "MT"),
    ("ERW-PIPE-50NB", "ERW Pipe 50NB Medium", "PIPE", "IS1239", "IS 1239", "7.85", "MT"),
    ("RHS-100X50-S355", "RHS 100x50x4 S355", "RHS", "S355", "EN 10219", "7.85", "MT"),
    ("SHS-75X75-S355", "SHS 75x75x4 S355", "SHS", "S355", "EN 10219", "7.85", "MT"),
    ("HR-COIL-E250", "HR Coil 3mm E250", "COIL", "E250", "IS 1079", "7.85", "MT"),
    ("TMT-FE500D-12", "TMT Rebar 12mm Fe500D", "REBAR", "FE500D", "IS 1786", "7.85", "MT"),
    ("CHK-PLT-5-E250", "Chequered Plate 5mm E250", "CHEQUERED", "E250", "IS 3502", "7.85", "MT"),
]


def seed_catalog(db: Session) -> None:
    for sku, name, form, grade, standard, density, unit in CATALOG:
        get_or_create(db, MaterialCatalog, sku=sku, defaults=dict(
            id=uid(f"catalog:{sku}"), name=name, form=form, grade=grade,
            standard=standard, density=Decimal(density), base_unit=unit))


def seed_org_materials(db: Session, org: Organization, prefix: str) -> dict[str, OrganizationMaterial]:
    mats: dict[str, OrganizationMaterial] = {}
    thresholds = {"BEAM": Decimal("20"), "PLATE": Decimal("15"), "REBAR": Decimal("25")}
    for sku, name, form, grade, standard, density, unit in CATALOG:
        cat = db.scalar(select(MaterialCatalog).where(MaterialCatalog.sku == sku))
        m, _ = get_or_create(db, OrganizationMaterial,
                             organization_id=org.id, sku=f"{prefix}-{sku}",
                             defaults=dict(
                                 id=uid(f"mat:{org.id}:{prefix}-{sku}"), catalog_id=cat.id,
                                 name=name, form=form, grade=grade, standard=standard,
                                 base_unit="MT", density=Decimal(density),
                                 specification={"dimensions": "standard section"},
                                 low_stock_threshold=thresholds.get(form, Decimal("10"))))
        mats[form] = m
        mats[f"{form}:{sku}"] = m
    return mats


def seed_warehouses(db: Session, org: Organization, tag: str) -> list[Warehouse]:
    w1, _ = get_or_create(db, Warehouse, organization_id=org.id, code=f"{tag}-W1",
                          defaults=dict(id=uid(f"wh:{org.id}:W1"),
                                        name=f"[DEMO] {tag} Main Yard",
                                        location="Bhiwandi, Maharashtra (fictional)"))
    w2, _ = get_or_create(db, Warehouse, organization_id=org.id, code=f"{tag}-W2",
                          defaults=dict(id=uid(f"wh:{org.id}:W2"),
                                        name=f"[DEMO] {tag} Depot",
                                        location="Pune, Maharashtra (fictional)"))
    return [w1, w2]


def seed_lots(db: Session, org: Organization, mats: dict, whs: list[Warehouse],
              plan: list[dict]) -> dict[str, StockLot]:
    """plan: [{key, form, wh(0|1), lot, heat, qty, reserved, quality, cost}]"""
    lots: dict[str, StockLot] = {}
    for i, p in enumerate(plan, start=1):
        mat = mats[p["form"]]
        lot, created = get_or_create(
            db, StockLot, organization_id=org.id, material_id=mat.id,
            warehouse_id=whs[p.get("wh", 0)].id, lot_number=p["lot"],
            defaults=dict(id=uid(f"lot:{org.id}:{p['lot']}"), heat_number=p.get("heat"),
                          quality_status=p.get("quality", "OK"),
                          on_hand_qty=Decimal("0"), reserved_qty=Decimal("0"),
                          unit="MT", unit_cost=Decimal(str(p["cost"])),
                          source={"kind": "SEED", "demo": True}))
        lots[p["key"]] = lot
        if created:
            qty = Decimal(str(p["qty"]))
            lot.on_hand_qty = qty
            lot.reserved_qty = Decimal(str(p.get("reserved", 0)))
            db.add(InventoryMovement(
                id=uid(f"mv:{org.id}:{p['lot']}"), organization_id=org.id,
                material_id=mat.id, warehouse_id=whs[p.get("wh", 0)].id, stock_lot_id=lot.id,
                movement_type="RECEIPT", quantity=qty, unit="MT", balance_after_on_hand=qty,
                reference={"kind": "SEED", "demo": True,
                           "note": "Opening demo stock (fictional)"}))
    return lots


def seed_suppliers(db: Session, org: Organization, tag: str,
                   specs: list[tuple]) -> list[Supplier]:
    out = []
    for code, name, city, lead, terms, caps, rating in specs:
        s, _ = get_or_create(db, Supplier, organization_id=org.id, code=code,
                             defaults=dict(
                                 id=uid(f"sup:{org.id}:{code}"), name=f"[DEMO] {name}",
                                 category="Steel supplier (fictional)", contact_name="Sales Desk",
                                 email=f"sales@{code.lower()}.example.invalid",
                                 phone="+91-00000-00000", city=city,
                                 payment_terms_days=terms, lead_time_days=lead,
                                 rating=Decimal(rating), material_capabilities=caps,
                                 is_demo=True))
        out.append(s)
    return out


def seed_customers(db: Session, org: Organization, specs: list[tuple]) -> list[Customer]:
    out = []
    for code, name, cat, terms in specs:
        c, _ = get_or_create(db, Customer, organization_id=org.id, code=code,
                             defaults=dict(
                                 id=uid(f"cus:{org.id}:{code}"), name=f"[DEMO] {name}",
                                 category=cat, gstin="27DEMO0000X1Z5", credit_terms_days=terms,
                                 is_demo=True))
        get_or_create(db, CustomerContact, organization_id=org.id, customer_id=c.id,
                      name="Purchase Manager",
                      defaults=dict(id=uid(f"cc:{org.id}:{code}"),
                                    email=f"pm@{code.lower()}.example.invalid",
                                    designation="Purchase Manager (fictional)"))
        out.append(c)
    return out


def seed_prices(db: Session) -> None:
    """Labeled SYNTHETIC historical observations (6 monthly points), tagged fictional."""
    src, _ = get_or_create(db, PriceSource, name="Demo Synthetic Feed (fictional)",
                           organization_id=None,
                           defaults=dict(id=uid("psrc:demo"), source_type="SYNTHETIC",
                                         provider_key="demo-synthetic", is_synthetic=True))
    series = [
        ("BEAM", "E250", "West India", ["54800", "55100", "54500", "55200", "55800", "56100"]),
        ("PLATE", "E250", "West India", ["53200", "53800", "53500", "54100", "54600", "54900"]),
        ("REBAR", "FE500D", "West India", ["51500", "51800", "52100", "51900", "52300", "52700"]),
        ("COIL", "E250", "West India", ["52600", "52900", "53100", "53400", "53200", "53600"]),
        ("RHS", "S355", "West India", ["58500", "58900", "59200", "59000", "59400", "59800"]),
    ]
    for form, grade, region, prices in series:
        for i, price in enumerate(prices):
            observed = TODAY - timedelta(days=(len(prices) - 1 - i) * 30)
            get_or_create(db, PriceObservation, material_form=form, grade=grade, region=region,
                          observed_on=observed, organization_id=None,
                          defaults=dict(id=uid(f"po:{form}:{grade}:{region}:{observed}"),
                                        source_id=src.id, dimension_note="standard section",
                                        price_per_unit=Decimal(price), unit="MT", currency="INR",
                                        is_synthetic=True))


def seed_quotation_chain(db: Session, org: Organization, customer: Customer, mat, *,
                         number: str, qty: str, unit_price: str, unit_cost: str,
                         status: str, with_order: bool, admin: User,
                         inquiry_ref: str) -> tuple[Quotation, SalesOrder | None]:
    """Deterministic inquiry → quotation → (optional) sales order chain."""
    inquiry, _ = get_or_create(db, CustomerInquiry, organization_id=org.id, reference=inquiry_ref,
                               defaults=dict(
                                   id=uid(f"inq:{org.id}:{inquiry_ref}"), customer_id=customer.id,
                                   source="MANUAL", status="WON" if with_order else "QUOTED",
                                   received_at=NOW - timedelta(days=20),
                                   notes="Demo inquiry (fictional)"))
    get_or_create(db, InquiryItem, organization_id=org.id, inquiry_id=inquiry.id,
                  description=mat.name,
                  defaults=dict(id=uid(f"inq-it:{org.id}:{inquiry_ref}"), material_id=mat.id,
                                form=mat.form, grade=mat.grade, quantity=Decimal(qty),
                                unit="MT", target_price=Decimal(unit_price)))
    q, created = get_or_create(db, Quotation, organization_id=org.id, number=number,
                               defaults=dict(
                                   id=uid(f"qt:{org.id}:{number}"), inquiry_id=inquiry.id,
                                   customer_id=customer.id, status=status, currency="INR",
                                   target_margin=Decimal("0.1275"), created_by=admin.id,
                                   valid_until=NOW + timedelta(days=15)))
    if not created:
        version = db.scalar(select(QuotationVersion).where(
            QuotationVersion.quotation_id == q.id).limit(1))
        so = db.scalar(select(SalesOrder).where(SalesOrder.quotation_id == q.id))
        return q, so
    qty_d, up, uc = Decimal(qty), Decimal(unit_price), Decimal(unit_cost)
    total_sell = qty_d * up
    total_cost = qty_d * uc
    est = CostEstimate(id=uid(f"ce:{org.id}:{number}"), organization_id=org.id,
                       context={"quotation_id": str(q.id)}, status="APPROVED",
                       material_cost=total_cost, total_cost=total_cost, currency="INR",
                       created_by=admin.id)
    db.add(est)
    db.flush()
    db.add(CostLine(id=uid(f"cl:{org.id}:{number}"), organization_id=org.id,
                    cost_estimate_id=est.id, category="MATERIAL", description=mat.name,
                    material_id=mat.id, quantity=qty_d, unit="MT", unit_cost=uc,
                    amount=total_cost, source={"basis": "demo-seed"}))
    ver = QuotationVersion(id=uid(f"qv:{org.id}:{number}"), organization_id=org.id,
                           quotation_id=q.id, version_no=1, status=status,
                           subtotal=total_cost, total_estimated_cost=total_cost,
                           total_selling_price=total_sell,
                           gross_margin_pct=(total_sell - total_cost) / total_sell,
                           cost_estimate_id=est.id,
                           approved_by=admin.id if status in ("APPROVED", "SENT", "ACCEPTED",
                                                              "CONVERTED") else None,
                           approved_at=NOW - timedelta(days=10) if status != "DRAFT" else None,
                           is_immutable=status != "DRAFT")
    db.add(ver)
    db.flush()
    db.add(QuotationItem(id=uid(f"qi:{org.id}:{number}"), organization_id=org.id,
                         quotation_version_id=ver.id, material_id=mat.id, description=mat.name,
                         form=mat.form, grade=mat.grade, quantity=qty_d, unit="MT",
                         unit_cost=uc, unit_price=up, line_estimated_cost=total_cost,
                         line_selling_price=total_sell,
                         available_qty=Decimal(qty) if with_order else Decimal("0"),
                         shortage_qty=Decimal("0")))
    if status == "PENDING_APPROVAL":
        db.add(Approval(id=uid(f"ap:{org.id}:{number}"), organization_id=org.id,
                        entity_type="quotation", entity_id=q.id, approval_type="QUOTATION",
                        requested_by=admin.id, status="PENDING"))
    so = None
    if with_order:
        so = SalesOrder(id=uid(f"so:{org.id}:{number}"), organization_id=org.id,
                        quotation_id=q.id, customer_id=customer.id,
                        number=number.replace("QTN", "SO"), status="CONFIRMED",
                        total_value=total_sell, order_date=NOW - timedelta(days=8),
                        delivery_date=NOW + timedelta(days=2),
                        notes="Demo sales order (fictional)")
        db.add(so)
        db.flush()
        db.add(SalesOrderItem(id=uid(f"soi:{org.id}:{number}"), organization_id=org.id,
                              sales_order_id=so.id, material_id=mat.id, description=mat.name,
                              quantity=qty_d, unit="MT", unit_price=up))
        q.status = "CONVERTED"
    return q, so
