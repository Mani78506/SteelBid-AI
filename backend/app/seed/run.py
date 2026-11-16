"""Seed runner. Usage: python -m app.seed.run

Idempotent: safe to run repeatedly. Refuses to run when DEMO_MODE=false (production).
All demo data is visibly fictional: [DEMO] prefixes, is_demo flags, labeled synthetic prices.
"""
from datetime import timedelta, datetime, timezone, date
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.core.security import hash_password
from app.models.identity import Membership, Organization, User
from app.models.procurement import (PurchaseOrder, PurchaseOrderItem, PurchaseRequest,
                                    PurchaseRequestItem, SupplierQuote)
from app.models.sales import SalesOrderItem
from app.models.fabrication import (BOMItem, BOMVersion, MaterialAllocation,
                                    ProductionOperation, QualityInspection, Routing, WorkOrder)
from app.models.inventory import Reservation, Warehouse, StockLot, InventoryMovement
from app.models.materials import OrganizationMaterial
from app.models.crm import Customer
from app.models.market import MarketPriceAlertRule, MarketSource, MarketSourceDocument, PriceObservation, PriceSource
from app.models.ops import CostEstimate, CostLine, Dispatch, DispatchItem, Invoice, Notification, Payment
from app.models.projects import BOQItem, Project, ProjectRequirement, Tender, TenderRequirementSnapshot, TenderSupplierSelection
from app.seed.demo import (CATALOG, NOW, TODAY, get_or_create, seed_catalog, seed_customers,
                           seed_lots, seed_org_materials, seed_prices, seed_quotation_chain,
                           seed_suppliers, seed_warehouses, uid)

settings = get_settings()
DEMO_PASSWORD_NOTE = "Demo passwords come from DEMO_ADMIN_PASSWORD env (default in .env.example)."


def _password() -> str:
    return settings.demo_admin_password


def seed_org(db, *, key: str, name: str, profiles: list[str], is_demo: bool = True):
    # The deterministic key is the durable fixture identity. Looking up by name
    # made a presentation-name change try to insert the same UUID again.
    org, created = get_or_create(db, Organization, id=uid(f"org:{key}"),
                                 defaults=dict(name=name, business_profiles=profiles,
                                               currency_code="INR", timezone="Asia/Kolkata",
                                               is_demo=is_demo))
    if not created:
        org.name = name
        org.business_profiles = profiles
        org.is_demo = is_demo
    return org


def seed_user(db, email: str, full_name: str, orgs_roles: list[tuple]) -> User:
    user, created = get_or_create(db, User, email=email,
                                  defaults=dict(id=uid(f"user:{email}"), full_name=full_name,
                                                password_hash=hash_password(_password()),
                                                is_demo=True))
    for org, role in orgs_roles:
        get_or_create(db, Membership, organization_id=org.id, user_id=user.id,
                      defaults=dict(id=uid(f"mem:{org.id}:{email}"), role=role))
    return user


def seed_apex_trader(db, admin: User) -> Organization:
    """PRIMARY DEMO ORG — carries the 100 MT inquiry workflow dataset."""
    org = seed_org(db, key="apex", name="[DEMO] Apex Steel Traders Pvt Ltd",
                   profiles=["TRADER", "DISTRIBUTOR"])
    mats = seed_org_materials(db, org, "APX")
    whs = seed_warehouses(db, org, "APX")
    # BEAM E250: 40 MT eligible OK lot (+15 MT quarantined); PLATE: 25 MT with 8 reserved;
    # REBAR: 0-ish shortage example; others nominal.
    beam_key = next(k for k in mats if k.startswith("BEAM:"))
    beam = mats[beam_key]
    lots = seed_lots(db, org, mats, whs, [
        {"key": "beam_ok", "form": beam_key, "wh": 0, "lot": "APX-LOT-001", "heat": "HT-2401",
         "qty": "40", "cost": "54500"},
        {"key": "beam_q", "form": beam_key, "wh": 0, "lot": "APX-LOT-002", "heat": "HT-2389",
         "qty": "15", "quality": "QUARANTINED", "cost": "53200"},
        {"key": "plate_ok", "form": "PLATE:MS-PLT-E250-10", "wh": 0, "lot": "APX-LOT-003",
         "heat": "HT-2380", "qty": "25", "reserved": "8", "cost": "53100"},
        {"key": "rebar_low", "form": "REBAR:TMT-FE500D-12", "wh": 1, "lot": "APX-LOT-010",
         "heat": "HT-2404", "qty": "6", "cost": "51200"},
        {"key": "ch_ok", "form": "CHANNEL:ISMC-150-E250", "wh": 1, "lot": "APX-LOT-004",
         "heat": "HT-2366", "qty": "18", "cost": "55800"},
        {"key": "ang_ok", "form": "ANGLE:ISA-50505-E250", "wh": 0, "lot": "APX-LOT-005",
         "heat": "HT-2340", "qty": "22", "cost": "54100"},
        {"key": "shs_ok", "form": "SHS:SHS-75X75-S355", "wh": 1, "lot": "APX-LOT-006",
         "heat": "HT-2399", "qty": "12", "cost": "59100"},
        {"key": "coil_ok", "form": "COIL:HR-COIL-E250", "wh": 1, "lot": "APX-LOT-007",
         "heat": "HT-2410", "qty": "30", "cost": "53300"},
        {"key": "pipe_ok", "form": "PIPE:ERW-PIPE-50NB", "wh": 0, "lot": "APX-LOT-008",
         "heat": "HT-2415", "qty": "9", "cost": "56200"},
        {"key": "chk_ok", "form": "CHEQUERED:CHK-PLT-5-E250", "wh": 1, "lot": "APX-LOT-009",
         "heat": "HT-2341", "qty": "7", "cost": "54800"},
        {"key": "rhs_ok", "form": "RHS:RHS-100X50-S355", "wh": 0, "lot": "APX-LOT-011",
         "heat": "HT-2421", "qty": "11", "cost": "59400"},
        {"key": "plt20_ok", "form": "PLATE:MS-PLT-E250-20", "wh": 0, "lot": "APX-LOT-012",
         "heat": "HT-2428", "qty": "14", "cost": "53600"},
    ])
    suppliers = seed_suppliers(db, org, "APX", [
        ("SUP-DEC", "Deccan Steel Supply Co", "Mumbai (fictional)", 10, 30,
         ["BEAM", "PLATE", "CHANNEL", "ANGLE"], "4.20"),
        ("SUP-WES", "Western Alloys & Metals", "Ahmedabad (fictional)", 15, 45,
         ["BEAM", "SHS", "RHS", "COIL"], "3.80"),
        ("SUP-SAH", "Sahyadri Iron Traders", "Pune (fictional)", 7, 15,
         ["BEAM", "PLATE", "REBAR", "CHEQUERED"], "4.50"),
    ])
    # Three competing quotes for BEAM E250 (60 MT) — landed: 56,300 / 56,500 / 56,200.
    quotes = [
        (suppliers[0], "55500", "800", "10"),
        (suppliers[1], "54900", "1600", "15"),
        (suppliers[2], "56200", "0", "7"),
    ]
    for i, (sup, price, freight, lead) in enumerate(quotes, start=1):
        get_or_create(db, SupplierQuote, organization_id=org.id, supplier_id=sup.id,
                      material_id=beam.id,
                      defaults=dict(id=uid(f"sq:{org.id}:beam:{i}"), rfq_id=None,
                                    quantity=Decimal("60"), unit="MT",
                                    unit_price=Decimal(price), currency="INR",
                                    freight_per_unit=Decimal(freight), tax_pct=Decimal("0.18"),
                                    tax_recoverable=True, payment_terms_days=30,
                                    lead_time_days=int(lead),
                                    valid_until=TODAY + timedelta(days=20), status="OPEN"))
    customers = seed_customers(db, org, [
        ("CUS-KON", "Konkan Railway Projects Ltd", "Contractor", 45),
        ("CUS-GAT", "Gateway Industrial Estates", "Industrial buyer", 30),
        ("CUS-VNS", "Vansh Constructions", "Contractor", 30),
        ("CUS-MTW", "Metro Water Works Corp", "Government utility", 60),
        ("CUS-SHV", "Shivalik Bridge Consortium", "Infrastructure JV", 60),
    ])
    # Historical chains for dashboard richness
    seed_quotation_chain(db, org, customers[1], mats["PLATE:MS-PLT-E250-10"],
                         number="QTN-2026-0001", qty="8", unit_price="63400",
                         unit_cost="53100", status="CONVERTED", with_order=True,
                         admin=admin, inquiry_ref="INQ-2026-0007")
    so2_q, so2 = seed_quotation_chain(db, org, customers[2], mats["CHANNEL:ISMC-150-E250"],
                                      number="QTN-2026-0002", qty="12", unit_price="65500",
                                      unit_cost="55800", status="CONVERTED", with_order=True,
                                      admin=admin, inquiry_ref="INQ-2026-0009")
    seed_quotation_chain(db, org, customers[0], mats["ANGLE:ISA-50505-E250"],
                         number="QTN-2026-0003", qty="10", unit_price="61200",
                         unit_cost="54100", status="PENDING_APPROVAL", with_order=False,
                         admin=admin, inquiry_ref="INQ-2026-0012")
    seed_quotation_chain(db, org, customers[3], mats["COIL:HR-COIL-E250"],
                         number="QTN-2026-0004", qty="25", unit_price="61800",
                         unit_cost="53300", status="SENT", with_order=False,
                         admin=admin, inquiry_ref="INQ-2026-0015")

    # Open shortage PO commitments (for purchase-commitments KPI + receipts demo)
    pr, pr_created = get_or_create(db, PurchaseRequest, organization_id=org.id,
                                   number="PR-2026-0001",
                                   defaults=dict(id=uid(f"pr:{org.id}:PR-2026-0001"),
                                                 status="ORDERED", source_type="SHORTAGE",
                                                 context={"reason": "demo replenishment",
                                                          "demo": True},
                                                 needed_by=TODAY + timedelta(days=12),
                                                 created_by=admin.id))
    if pr_created:
        db.add(PurchaseRequestItem(id=uid(f"pri:{org.id}:PR-2026-0001"),
                                   organization_id=org.id, purchase_request_id=pr.id,
                                   material_id=mats["REBAR:TMT-FE500D-12"].id,
                                   quantity=Decimal("20"), unit="MT",
                                   required_by=TODAY + timedelta(days=12)))
    po, po_created = get_or_create(db, PurchaseOrder, organization_id=org.id,
                                   number="PO-2026-0001",
                                   defaults=dict(
                                       id=uid(f"po:{org.id}:PO-2026-0001"),
                                       supplier_id=suppliers[2].id,
                                       purchase_request_id=pr.id, status="APPROVED",
                                       total_value=Decimal("1024000"),
                                       expected_delivery=TODAY + timedelta(days=12),
                                       approved_by=admin.id, approved_at=NOW - timedelta(days=3),
                                       created_by=admin.id))
    if po_created:
        db.add(PurchaseOrderItem(id=uid(f"poi:{org.id}:PO-2026-0001"), organization_id=org.id,
                                 purchase_order_id=po.id,
                                 material_id=mats["REBAR:TMT-FE500D-12"].id,
                                 quantity=Decimal("20"), unit="MT",
                                 unit_price=Decimal("51200")))

    # Overdue receivable (KPI) + partially paid
    from app.models.sales import SalesOrder
    so1 = db.scalar(select(SalesOrder).where(SalesOrder.organization_id == org.id,
                                             SalesOrder.number == "SO-2026-0001"))
    inv, inv_created = get_or_create(db, Invoice, organization_id=org.id, invoice_type="SALES",
                                     number="INV-2026-0001",
                                     defaults=dict(
                                         id=uid(f"inv:{org.id}:INV-2026-0001"),
                                         customer_id=customers[1].id,
                                         sales_order_id=so1.id if so1 else None,
                                         issue_date=TODAY - timedelta(days=75),
                                         due_date=TODAY - timedelta(days=30),
                                         subtotal=Decimal("507200"), tax_amount=Decimal("91296"),
                                         total=Decimal("598496"), status="OVERDUE"))
    if inv_created:
        db.add(Payment(id=uid(f"pay:{org.id}:INV-2026-0001"), organization_id=org.id,
                       invoice_id=inv.id, amount=Decimal("200000"),
                       paid_on=TODAY - timedelta(days=40), method="NEFT",
                       reference="DEMO-NEFT-001"))
    inv2, _ = get_or_create(db, Invoice, organization_id=org.id, invoice_type="SALES",
                            number="INV-2026-0004",
                            defaults=dict(id=uid(f"inv:{org.id}:INV-2026-0004"),
                                          customer_id=customers[2].id, status="ISSUED",
                                          issue_date=TODAY - timedelta(days=5),
                                          due_date=TODAY + timedelta(days=25),
                                          subtotal=Decimal("786000"), tax_amount=Decimal("141480"),
                                          total=Decimal("927480")))

    # A planned dispatch against SO2 (reserve some of so2's channel stock)
    if so2:
        so2_items = db.scalars(select(SalesOrderItem).where(
            SalesOrderItem.sales_order_id == so2.id)).all()
        if so2_items:
            item = so2_items[0]
            ch_lot = lots["ch_ok"]
            res, res_created = get_or_create(
                db, Reservation, organization_id=org.id, stock_lot_id=ch_lot.id,
                idempotency_key=f"seed:{org.id}:so2",
                defaults=dict(id=uid(f"res:{org.id}:so2"), material_id=ch_lot.material_id,
                              warehouse_id=ch_lot.warehouse_id, quantity=Decimal("6"),
                              status="ACTIVE",
                              context={"sales_order_id": str(so2.id),
                                       "sales_order_item_id": str(item.id)},
                              created_by=admin.id))
            if res_created:
                ch_lot.reserved_qty = ch_lot.reserved_qty + Decimal("6")
                item.reserved_qty = item.reserved_qty + Decimal("6")
            dsp, dsp_created = get_or_create(db, Dispatch, organization_id=org.id,
                                             number="DSP-2026-0001",
                                             defaults=dict(
                                                 id=uid(f"dsp:{org.id}:DSP-2026-0001"),
                                                 sales_order_id=so2.id, warehouse_id=whs[1].id,
                                                 status="PLANNED", vehicle="MH-04-DEMO-01",
                                                 transporter="[DEMO] Western Carriers",
                                                 dispatch_date=TODAY + timedelta(days=1)))
            if dsp_created:
                db.add(DispatchItem(id=uid(f"dspi:{org.id}:DSP-2026-0001"),
                                    organization_id=org.id, dispatch_id=dsp.id,
                                    sales_order_item_id=item.id, stock_lot_id=ch_lot.id,
                                    material_id=ch_lot.material_id, quantity=Decimal("6"),
                                    unit="MT"))
    return org


def seed_metro_distributor(db, admin: User) -> Organization:
    org = seed_org(db, key="metro", name="[DEMO] Metro Steel Distributors Pvt Ltd",
                   profiles=["DISTRIBUTOR", "TRADER"])
    mats = seed_org_materials(db, org, "MET")
    whs = seed_warehouses(db, org, "MET")
    plan_forms = ["PLATE:MS-PLT-E250-10", "BEAM:ISMB-200-E250", "CHANNEL:ISMC-150-E250",
                  "ANGLE:ISA-50505-E250", "PIPE:ERW-PIPE-50NB", "RHS:RHS-100X50-S355",
                  "SHS:SHS-75X75-S355", "COIL:HR-COIL-E250", "REBAR:TMT-FE500D-12",
                  "CHEQUERED:CHK-PLT-5-E250", "PLATE:MS-PLT-E250-20", "BEAM:ISMB-300-E250"]
    lots_plan = []
    for i, fkey in enumerate(plan_forms):
        wh = i % 2
        lots_plan.append({"key": f"m{i}", "form": fkey, "wh": wh,
                          "lot": f"MET-LOT-{i + 1:03d}", "heat": f"HT-{2400 + i}",
                          "qty": str(10 + (i * 3) % 27),
                          "quality": "QUARANTINED" if i == 4 else "OK",
                          "reserved": "4" if i == 2 else "0",
                          "cost": str(52000 + i * 450)})
    lots_plan += [  # reach 15 stock lots
        {"key": "m12", "form": "PLATE:MS-PLT-E250-10", "wh": 0, "lot": "MET-LOT-013",
         "heat": "HT-2430", "qty": "16", "cost": "53300"},
        {"key": "m13", "form": "CHANNEL:ISMC-150-E250", "wh": 1, "lot": "MET-LOT-014",
         "heat": "HT-2431", "qty": "19", "cost": "55400"},
        {"key": "m14", "form": "ANGLE:ISA-50505-E250", "wh": 0, "lot": "MET-LOT-015",
         "heat": "HT-2432", "qty": "13", "quality": "REJECTED", "cost": "51500"},
    ]
    seed_lots(db, org, mats, whs, lots_plan)
    suppliers = seed_suppliers(db, org, "MET", [
        ("SUP-KAL", "Kalinga Steels Corp", "Raipur (fictional)", 12, 30,
         ["PLATE", "COIL", "CHEQUERED"], "4.10"),
        ("SUP-NRV", "Narmada Rolling Mills", "Indore (fictional)", 9, 30,
         ["BEAM", "CHANNEL", "ANGLE", "REBAR"], "4.30"),
        ("SUP-VEL", "Vellore Tube House", "Chennai (fictional)", 14, 45,
         ["PIPE", "RHS", "SHS"], "3.90"),
    ])
    customers = seed_customers(db, org, [
        ("CUS-NPL", "Northern Precast Ltd", "Precaster", 30),
        ("CUS-BRT", "Bharat Rooflines", "PEB builder", 30),
        ("CUS-SFD", "Southern Frames & Decks", "Fabricator", 45),
    ])
    seed_quotation_chain(db, org, customers[0], mats["PLATE:MS-PLT-E250-10"],
                         number="QTN-2026-0001", qty="11", unit_price="62800",
                         unit_cost="52500", status="CONVERTED", with_order=True,
                         admin=admin, inquiry_ref="INQ-2026-0021")
    return org


def seed_precision_fabricator(db, admin: User) -> Organization:
    """Fabricator demo: approved BOM + in-progress work order with allocated material."""
    org = seed_org(db, key="precision", name="[DEMO] PrecisionSteel Fabricators Pvt Ltd",
                   profiles=["FABRICATOR", "TRADER"])
    mats = seed_org_materials(db, org, "PSF")
    whs = seed_warehouses(db, org, "PSF")
    lots = seed_lots(db, org, mats, whs, [
        {"key": "plt", "form": "PLATE:MS-PLT-E250-10", "wh": 0, "lot": "PSF-LOT-001",
         "heat": "HT-2501", "qty": "20", "cost": "53000"},
        {"key": "beam", "form": "BEAM:ISMB-200-E250", "wh": 0, "lot": "PSF-LOT-002",
         "heat": "HT-2502", "qty": "16", "cost": "54600"},
        {"key": "ch", "form": "CHANNEL:ISMC-150-E250", "wh": 1, "lot": "PSF-LOT-003",
         "heat": "HT-2503", "qty": "12", "cost": "55200"},
        {"key": "ang", "form": "ANGLE:ISA-50505-E250", "wh": 0, "lot": "PSF-LOT-004",
         "heat": "HT-2504", "qty": "15", "cost": "53900"},
        {"key": "plt20", "form": "PLATE:MS-PLT-E250-20", "wh": 1, "lot": "PSF-LOT-005",
         "heat": "HT-2505", "qty": "9", "quality": "QUARANTINED", "cost": "52800"},
        {"key": "rhs", "form": "RHS:RHS-100X50-S355", "wh": 0, "lot": "PSF-LOT-006",
         "heat": "HT-2506", "qty": "10", "cost": "59000"},
        {"key": "shs", "form": "SHS:SHS-75X75-S355", "wh": 1, "lot": "PSF-LOT-007",
         "heat": "HT-2507", "qty": "8", "cost": "59200"},
        {"key": "coil", "form": "COIL:HR-COIL-E250", "wh": 1, "lot": "PSF-LOT-008",
         "heat": "HT-2508", "qty": "24", "cost": "53100"},
        {"key": "pipe", "form": "PIPE:ERW-PIPE-50NB", "wh": 0, "lot": "PSF-LOT-009",
         "heat": "HT-2509", "qty": "6", "cost": "55900"},
        {"key": "chk", "form": "CHEQUERED:CHK-PLT-5-E250", "wh": 1, "lot": "PSF-LOT-010",
         "heat": "HT-2510", "qty": "5", "cost": "54700"},
        {"key": "rebar", "form": "REBAR:TMT-FE500D-12", "wh": 1, "lot": "PSF-LOT-011",
         "heat": "HT-2511", "qty": "14", "cost": "51400"},
        {"key": "beam300", "form": "BEAM:ISMB-300-E250", "wh": 0, "lot": "PSF-LOT-012",
         "heat": "HT-2512", "qty": "11", "cost": "55200"},
        {"key": "plt2", "form": "PLATE:MS-PLT-E250-10", "wh": 1, "lot": "PSF-LOT-013",
         "heat": "HT-2513", "qty": "17", "cost": "53100"},
        {"key": "ang2", "form": "ANGLE:ISA-50505-E250", "wh": 1, "lot": "PSF-LOT-014",
         "heat": "HT-2514", "qty": "13", "cost": "54100"},
        {"key": "shs2", "form": "SHS:SHS-75X75-S355", "wh": 0, "lot": "PSF-LOT-015",
         "heat": "HT-2515", "qty": "9", "reserved": "4", "cost": "59100"},
    ])
    suppliers = seed_suppliers(db, org, "PSF", [
        ("SUP-AKP", "Akash Profiles & Plates", "Nagpur (fictional)", 8, 30,
         ["PLATE", "CHEQUERED", "COIL"], "4.40"),
        ("SUP-TTN", "Titan Structural Supply", "Surat (fictional)", 11, 30,
         ["BEAM", "CHANNEL", "ANGLE"], "4.00"),
        ("SUP-OMX", "Omex Hollow Sections", "Bhilai (fictional)", 13, 45,
         ["RHS", "SHS", "PIPE"], "4.10"),
    ])
    customers = seed_customers(db, org, [
        ("CUS-INP", "Indus Power Projects", "EPC", 45),
        ("CUS-GRN", "GreenField Cement Works", "Industrial", 60),
        ("CUS-CTY", "CityMall Developers", "Real estate", 30),
    ])
    # Approved BOM: heavy base frame (plate + beams + gussets)
    bom, bom_created = get_or_create(db, BOMVersion, organization_id=org.id, bom_code="BOM-BF-100",
                                     version_no=1,
                                     defaults=dict(
                                         id=uid(f"bom:{org.id}:BOM-BF-100:1"),
                                         product_name="[DEMO] Heavy base frame (10 units)",
                                         status="APPROVED", approved_by=admin.id,
                                         approved_at=NOW - timedelta(days=6),
                                         estimated_material_cost=Decimal("2136330"),
                                         estimated_total_cost=Decimal("2238330")))
    if bom_created:
        for mat_key, qty in (("plt", "18.5"), ("beam", "12.0"), ("ch", "6.4"), ("ang", "2.5")):
            db.add(BOMItem(id=uid(f"bomi:{org.id}:{mat_key}"), organization_id=org.id,
                           bom_version_id=bom.id, material_id=lots[mat_key].material_id,
                           quantity=Decimal(qty), unit="MT",
                           theoretical_waste_pct=Decimal("0.04")))
        for seq, op, wc, hrs, rate in (
                (1, "CUTTING", "CNC plasma table", Decimal("32"), Decimal("950")),
                (2, "DRILLING", "Radial drill", Decimal("18"), Decimal("650")),
                (3, "WELDING", "MIG bay 2", Decimal("46"), Decimal("850")),
                (4, "PAINTING", "Paint booth", Decimal("12"), Decimal("700")),
                (5, "INSPECTION", "QC lab", Decimal("6"), Decimal("600"))):
            db.add(Routing(id=uid(f"rt:{org.id}:{seq}"), organization_id=org.id,
                           bom_version_id=bom.id, sequence=seq, operation_type=op,
                           work_center=wc, est_hours=hrs, rate_per_hour=rate))
    wo, wo_created = get_or_create(db, WorkOrder, organization_id=org.id, number="WO-2026-0001",
                                   defaults=dict(
                                       id=uid(f"wo:{org.id}:WO-2026-0001"),
                                       bom_version_id=bom.id, status="IN_PROGRESS",
                                       planned_qty=Decimal("10"),
                                       produced_qty=Decimal("0"),
                                       start_date=TODAY - timedelta(days=4),
                                       due_date=TODAY + timedelta(days=9),
                                       actual_material_cost=Decimal("0"),
                                       actual_labour_cost=Decimal("30400")))
    if wo_created:
        routings = db.scalars(select(Routing).where(Routing.bom_version_id == bom.id)
                              .order_by(Routing.sequence)).all()
        for rt in routings:
            status = {"CUTTING": "COMPLETED", "DRILLING": "IN_PROGRESS"}.get(
                rt.operation_type, "PENDING")
            db.add(ProductionOperation(
                id=uid(f"op:{org.id}:{rt.sequence}"), organization_id=org.id, work_order_id=wo.id,
                routing_id=rt.id, sequence=rt.sequence, operation_type=rt.operation_type,
                status=status,
                started_at=NOW - timedelta(days=4) if status != "PENDING" else None,
                completed_at=NOW - timedelta(days=3) if status == "COMPLETED" else None,
                actual_hours=Decimal("32") if status == "COMPLETED" else None,
                operator="R. Kumar (demo)" if status != "PENDING" else None))
        plt_lot = lots["plt"]
        alloc = MaterialAllocation(
            id=uid(f"alloc:{org.id}:plt"), organization_id=org.id, work_order_id=wo.id,
            stock_lot_id=plt_lot.id, material_id=plt_lot.material_id,
            allocated_qty=Decimal("8"), consumed_qty=Decimal("0"), status="ALLOCATED")
        db.add(alloc)
        res = Reservation(id=uid(f"res:{org.id}:wo1"), organization_id=org.id,
                          stock_lot_id=plt_lot.id, material_id=plt_lot.material_id,
                          warehouse_id=plt_lot.warehouse_id, quantity=Decimal("8"),
                          status="ACTIVE",
                          context={"work_order_id": str(wo.id)}, created_by=admin.id,
                          idempotency_key=f"seed:{org.id}:wo1")
        plt_lot.reserved_qty = plt_lot.reserved_qty + Decimal("8")
        db.add(res)
        db.add(QualityInspection(id=uid(f"qi:{org.id}:wo1"), organization_id=org.id,
                                 work_order_id=wo.id, inspection_type="Dimensional check",
                                 result="PASS", inspector="QC-01 (demo)",
                                 notes="Cut sizes within tolerance (demo record)"))
    # Tender demo for the fabricator
    project, _ = get_or_create(db, Project, organization_id=org.id, code="PRJ-PLT-01",
                               defaults=dict(
                                   id=uid(f"prj:{org.id}:PLT01"),
                                   name="[DEMO] Industrial steel platform — GreenField Cement",
                                   customer_id=customers[1].id, project_type="INDUSTRIAL",
                                   location="Gulbarga (fictional)",
                                   estimated_value=Decimal("4800000"), status="ACTIVE"))
    get_or_create(db, Tender, organization_id=org.id, number="TND-2026-0001",
                  defaults=dict(id=uid(f"tnd:{org.id}:TND-2026-0001"), project_id=project.id,
                                title="[DEMO] Fabricated girder supply — 60 MT",
                                customer="GreenField Cement Works (fictional)",
                                project_type="FABRICATION", location="Gulbarga (fictional)",
                                submission_deadline=NOW + timedelta(days=11),
                                estimated_value=Decimal("3900000"),
                                description="Demo tender (fictional) — fabricated girders ISMB 300.",
                                status="ESTIMATING"))
    return org


def seed_railbuild_contractor(db, admin: User) -> Organization:
    """Contractor demo: railway station + bridge tenders with BOQ lines."""
    org = seed_org(db, key="railbuild", name="[DEMO] RailBuild Infrastructure Pvt Ltd",
                   profiles=["CONTRACTOR", "TRADER"])
    mats = seed_org_materials(db, org, "RBL")
    whs = seed_warehouses(db, org, "RBL")
    seed_lots(db, org, mats, whs, [
        {"key": "plt", "form": "PLATE:MS-PLT-E250-10", "wh": 0, "lot": "RBL-LOT-001",
         "heat": "HT-2601", "qty": "22", "cost": "53000"},
        {"key": "beam", "form": "BEAM:ISMB-200-E250", "wh": 0, "lot": "RBL-LOT-002",
         "heat": "HT-2602", "qty": "26", "cost": "54400"},
        {"key": "beam300", "form": "BEAM:ISMB-300-E250", "wh": 1, "lot": "RBL-LOT-003",
         "heat": "HT-2603", "qty": "18", "cost": "55100"},
        {"key": "ch", "form": "CHANNEL:ISMC-150-E250", "wh": 0, "lot": "RBL-LOT-004",
         "heat": "HT-2604", "qty": "14", "cost": "55300"},
        {"key": "ang", "form": "ANGLE:ISA-50505-E250", "wh": 1, "lot": "RBL-LOT-005",
         "heat": "HT-2605", "qty": "19", "cost": "53800"},
        {"key": "plt20", "form": "PLATE:MS-PLT-E250-20", "wh": 0, "lot": "RBL-LOT-006",
         "heat": "HT-2606", "qty": "8", "quality": "QUARANTINED", "cost": "52600"},
        {"key": "rebar", "form": "REBAR:TMT-FE500D-12", "wh": 1, "lot": "RBL-LOT-007",
         "heat": "HT-2607", "qty": "42", "reserved": "12", "cost": "51300"},
        {"key": "coil", "form": "COIL:HR-COIL-E250", "wh": 1, "lot": "RBL-LOT-008",
         "heat": "HT-2608", "qty": "21", "cost": "53200"},
        {"key": "rhs", "form": "RHS:RHS-100X50-S355", "wh": 0, "lot": "RBL-LOT-009",
         "heat": "HT-2609", "qty": "9", "cost": "58900"},
        {"key": "shs", "form": "SHS:SHS-75X75-S355", "wh": 1, "lot": "RBL-LOT-010",
         "heat": "HT-2610", "qty": "7", "cost": "59300"},
        {"key": "pipe", "form": "PIPE:ERW-PIPE-50NB", "wh": 0, "lot": "RBL-LOT-011",
         "heat": "HT-2611", "qty": "5", "cost": "56100"},
        {"key": "chk", "form": "CHEQUERED:CHK-PLT-5-E250", "wh": 1, "lot": "RBL-LOT-012",
         "heat": "HT-2612", "qty": "6", "cost": "54600"},
        {"key": "plt2", "form": "PLATE:MS-PLT-E250-10", "wh": 1, "lot": "RBL-LOT-013",
         "heat": "HT-2613", "qty": "12", "cost": "52900"},
        {"key": "beam2", "form": "BEAM:ISMB-200-E250", "wh": 1, "lot": "RBL-LOT-014",
         "heat": "HT-2614", "qty": "10", "cost": "54500"},
        {"key": "ang2", "form": "ANGLE:ISA-50505-E250", "wh": 0, "lot": "RBL-LOT-015",
         "heat": "HT-2615", "qty": "11", "cost": "54000"},
    ])
    suppliers = seed_suppliers(db, org, "RBL", [
        ("SUP-STW", "SteelWorks India Ltd", "Kolkata (fictional)", 15, 45,
         ["BEAM", "PLATE", "CHANNEL", "ANGLE"], "4.60"),
        ("SUP-EAS", "Eastern Structurals", "Jamshedpur (fictional)", 10, 30,
         ["BEAM", "PLATE"], "4.30"),
        ("SUP-JRF", "JR Fasteners & Steel", "Nagpur (fictional)", 6, 15,
         ["REBAR", "ANGLE", "CHANNEL"], "4.00"),
    ])
    customers = seed_customers(db, org, [
        ("CUS-IRW", "Indian Rail Works Authority", "Government", 90),
        ("CUS-SHB", "State Highway Board", "Government", 60),
        ("CUS-PRT", "Port Trust Engineering", "PSU", 60),
    ])
    p1, _ = get_or_create(db, Project, organization_id=org.id, code="PRJ-RST-01",
                          defaults=dict(
                              id=uid(f"prj:{org.id}:RST01"),
                              name="[DEMO] Seawoods station concourse steelwork",
                              customer_id=customers[0].id, project_type="RAILWAY",
                              location="Navi Mumbai (fictional)",
                              estimated_value=Decimal("12500000"), status="ACTIVE"))
    p2, _ = get_or_create(db, Project, organization_id=org.id, code="PRJ-BRG-02",
                          defaults=dict(
                              id=uid(f"prj:{org.id}:BRG02"),
                              name="[DEMO] Ulhas creek bridge steelworks",
                              customer_id=customers[1].id, project_type="BRIDGE",
                              location="Thane (fictional)",
                              estimated_value=Decimal("21000000"), status="ACTIVE"))
    t1, t1_created = get_or_create(db, Tender, organization_id=org.id, number="TND-2026-0001",
                                   defaults=dict(
                                       id=uid(f"tnd:{org.id}:TND-2026-0001"), project_id=p1.id,
                                       title="[DEMO] Seawoods station — structural steel supply "
                                             "& erection (145 MT)",
                                       customer="Indian Rail Works Authority (fictional)",
                                       project_type="RAILWAY", location="Navi Mumbai (fictional)",
                                       submission_deadline=NOW + timedelta(days=5),
                                       estimated_value=Decimal("10800000"),
                                       description="Demo tender (fictional). Scope: station "
                                                   "concourse columns, beams and roof trusses.",
                                       status="ESTIMATING"))
    if t1_created:
        boq_rows = [
            ("1.1", "ISMB 300 columns E250 grade IS 2062, length 8m", "BEAM", "E250", "38"),
            ("1.2", "ISMB 200 roof beams E250", "BEAM", "E250", "52"),
            ("1.3", "MS Plate 20mm E250 for base plates and gussets", "PLATE", "E250", "21"),
            ("1.4", "ISMC 150 purlins E250", "CHANNEL", "E250", "18"),
            ("1.5", "ISA 50x50x5 bracings E250", "ANGLE", "E250", "16"),
        ]
        beam300 = mats["BEAM:ISMB-300-E250"]
        beam = mats["BEAM:ISMB-200-E250"]
        plt20 = mats["PLATE:MS-PLT-E250-20"]
        ch = mats["CHANNEL:ISMC-150-E250"]
        ang = mats["ANGLE:ISA-50505-E250"]
        for line_no, desc, form, grade, qty in boq_rows:
            mat = {"1.1": beam300, "1.2": beam, "1.3": plt20, "1.4": ch, "1.5": ang}[line_no]
            db.add(BOQItem(id=uid(f"boq:{org.id}:{line_no}"), organization_id=org.id,
                           tender_id=t1.id, line_no=line_no, raw_description=desc,
                           form=form, grade=grade, specification={}, quantity=Decimal(qty),
                           unit="MT", material_id=mat.id, review_status="CONFIRMED",
                           source="AI", page_ref="p.3"))
        for mat_id, qty in ((beam300.id, "38"), (beam.id, "52"), (plt20.id, "21"),
                            (ch.id, "18"), (ang.id, "16")):
            db.add(ProjectRequirement(
                id=uid(f"prq:{org.id}:{mat_id}"), organization_id=org.id, project_id=p1.id,
                material_id=mat_id, quantity=Decimal(qty), unit="MT",
                required_by=TODAY + timedelta(days=45), source="BOQ"))
    get_or_create(db, Tender, organization_id=org.id, number="TND-2026-0002",
                  defaults=dict(id=uid(f"tnd:{org.id}:TND-2026-0002"), project_id=p2.id,
                                title="[DEMO] Ulhas creek bridge — steel girders & bracing",
                                customer="State Highway Board (fictional)", project_type="BRIDGE",
                                location="Thane (fictional)",
                                submission_deadline=NOW + timedelta(days=27),
                                estimated_value=Decimal("18400000"),
                                description="Demo tender (fictional) — plate girders, cross "
                                            "bracing, bearings.",
                                status="IN_REVIEW"))
    return org


def seed_market_showcase(db, admin: User) -> Organization:
    """Isolated persisted demo: 200 MT tender / 75 MT eligible / 125 MT shortage."""
    org = seed_org(db, key="market-showcase", name="[DEMO] SteelBid Market Showcase", profiles=["CONTRACTOR", "TRADER"])
    mats, whs = seed_org_materials(db, org, "MKT"), seed_warehouses(db, org, "MKT")
    lots = seed_lots(db, org, mats, whs, [
        {"key":"beam","form":"BEAM:ISMB-200-E250","lot":"MKT-B-001","qty":"40","cost":"55800"},
        {"key":"plate","form":"PLATE:MS-PLT-E250-10","lot":"MKT-P-001","qty":"25","cost":"54800"},
        {"key":"channel","form":"CHANNEL:ISMC-150-E250","lot":"MKT-C-001","qty":"10","cost":"55200"}])
    src, _ = get_or_create(db, PriceSource, organization_id=org.id, name="Synthetic Demo Data — SteelBid fixture",
        defaults=dict(id=uid(f"src:{org.id}"), source_type="SYNTHETIC", provider_key="demo-fixture", is_synthetic=True))
    # Deterministic, persisted one-year histories.  These are demonstration
    # fixtures only: they remain tenant-scoped and are never mixed into a
    # customer or provider source.
    market = [("HRC", "E250", 56000), ("CRC", "E350", 58500), ("TMT", "FE500D", 52700),
              ("BILLET", "FE500", 52000), ("SCRAP", "IS2062", 42000), ("PLATE", "E250", 54900),
              ("STRUCTURAL", "E250", 56100), ("BEAM", "E250", 56200), ("CHANNEL", "E250", 55200),
              ("ANGLE", "E250", 54800), ("WIRE_ROD", "FE500D", 53100), ("GALVANIZED", "E350", 62100)]
    regional_adjustment = {"North India": 650, "South India": -300, "East India": -850,
                           "West India": 0, "Central India": 280}
    for form, grade, base in market:
      for region, adjustment in regional_adjustment.items():
        # Keep the primary West-India series daily for a detailed chart and
        # use weekly regional comparisons to keep the repeatable seed quick.
        for i in (range(366) if region == "West India" else range(0, 366, 7)):
            observed = TODAY - timedelta(days=365-i)
            # Deterministic quarterly cycles: recovery, peak, correction and
            # stability.  This deliberately avoids a fabricated monotonic trend.
            quarter = i // 91
            quarter_move = (-1100, 1400, -1750, 900, 250)[min(quarter, 4)]
            monthly_wave = ((i // 30) % 4 - 1) * 180
            weekly_wave = ((i * 37) % 13 - 6) * 32
            price = Decimal(base + adjustment + quarter_move + monthly_wave + weekly_wave)
            row, _ = get_or_create(db, PriceObservation, organization_id=org.id, source_id=src.id, material_form=form, grade=grade,
                region=region, price_basis="EX_WORKS", unit="MT", currency="INR", observed_on=observed,
                defaults=dict(id=uid(f"price:{org.id}:{form}:{grade}:{region}:{observed}"), price_per_unit=price, is_synthetic=True))
            row.price_per_unit, row.is_synthetic = price, True
    get_or_create(db, MarketPriceAlertRule, organization_id=org.id, user_id=admin.id,
                  material_form="HRC", grade="E250", region="West India", currency="INR", unit="MT",
                  price_basis="EX_WORKS", source_id=src.id, price_condition="ABOVE",
                  defaults=dict(id=uid(f"alert:{org.id}:hrc-above"), price_threshold=Decimal("55500"),
                                movement_threshold_pct=None, is_active=True))
    suppliers = seed_suppliers(db, org, "MKT", [("SUP-A","[DEMO] Coastal Steel","Mumbai (synthetic)",8,30,["BEAM","PLATE","CHANNEL"],"4.4"),
        ("SUP-B","[DEMO] Western Rolling","Pune (synthetic)",11,45,["BEAM","PLATE","CHANNEL"],"4.1")])
    project, _ = get_or_create(db, Project, organization_id=org.id, code="PRJ-DEMO-200",
        defaults=dict(id=uid(f"project:{org.id}"),name="[DEMO] 200 MT structural package",project_type="INDUSTRIAL",location="Mumbai (synthetic)",estimated_value=Decimal("15000000"),status="ACTIVE"))
    tender, _ = get_or_create(db, Tender, organization_id=org.id, number="TND-DEMO-200MT",
        defaults=dict(id=uid(f"tender:{org.id}"),project_id=project.id,title="[DEMO] Structural steel package — 200 MT",customer="[DEMO] Showcase EPC",project_type="STRUCTURAL",location="Mumbai (synthetic)",submission_deadline=NOW+timedelta(days=7),estimated_value=Decimal("15000000"),description="Synthetic demo tender",status="ESTIMATING"))
    specs=[("1","BEAM:ISMB-200-E250","BEAM","E250","100","60"),("2","PLATE:MS-PLT-E250-10","PLATE","E250","60","35"),("3","CHANNEL:ISMC-150-E250","CHANNEL","E250","40","30")]
    total_material = Decimal("0")
    for line,key,form,grade,qty,shortage in specs:
        mat=mats[key]; q=Decimal(qty); unit_price=Decimal({"BEAM":"56800","PLATE":"55400","CHANNEL":"56000"}[form])
        bi,_=get_or_create(db,BOQItem,organization_id=org.id,tender_id=tender.id,line_no=line,
            defaults=dict(id=uid(f"boq:{org.id}:{line}"),raw_description=f"[DEMO] {form} {grade}",form=form,grade=grade,specification={"synthetic_demo":True},quantity=q,unit="MT",material_id=mat.id,review_status="CONFIRMED",source="MANUAL"))
        snap,_=get_or_create(db,TenderRequirementSnapshot,organization_id=org.id,tender_id=tender.id,source_boq_item_id=bi.id,version=1,
            defaults=dict(id=uid(f"snap:{org.id}:{line}"),material_id=mat.id,form=form,grade=grade,specification={"synthetic_demo":True},quantity=q,unit="MT",wastage_pct=Decimal("0"),engineering_status="APPROVED",approved_at=NOW,created_at=NOW,updated_at=NOW))
        quotes=[]
        for idx,supplier in enumerate(suppliers):
            quote,_=get_or_create(db,SupplierQuote,organization_id=org.id,supplier_id=supplier.id,material_id=mat.id,
                defaults=dict(id=uid(f"quote:{org.id}:{line}:{idx}"),quantity=q,unit="MT",unit_price=unit_price+idx*250,currency="INR",freight_per_unit=Decimal(str(400+idx*100)),tax_pct=Decimal("0.18"),tax_recoverable=True,payment_terms_days=30,lead_time_days=8+idx,valid_until=TODAY+timedelta(days=14),status="OPEN"))
            quotes.append(quote)
        best=quotes[0]; selected=Decimal(shortage); total_material += selected*(best.unit_price+best.freight_per_unit)
        get_or_create(db,TenderSupplierSelection,organization_id=org.id,tender_id=tender.id,tender_requirement_snapshot_id=snap.id,supplier_quote_id=best.id,
            defaults=dict(id=uid(f"selection:{org.id}:{line}"),selected_qty=selected,unit="MT",unit_price=best.unit_price,freight_per_unit=best.freight_per_unit,nonrecoverable_tax_per_unit=Decimal("0"),landed_cost_per_unit=best.unit_price+best.freight_per_unit,valid_until=best.valid_until,delivery_terms="[DEMO] Delivered site",status="SELECTED",selected_by=admin.id,created_at=NOW,updated_at=NOW))
    est, created=get_or_create(db,CostEstimate,organization_id=org.id,tender_id=tender.id,version=1,
        defaults=dict(id=uid(f"estimate:{org.id}"),context={"synthetic_demo":True,"note":"Draft costing — not an approved quotation"},status="DRAFT",material_cost=total_material,fabrication_cost=Decimal("1200000"),freight_cost=Decimal("180000"),overhead_cost=Decimal("420000"),total_cost=total_material+Decimal("1800000"),currency="INR",created_by=admin.id))
    if created:
        for category,amount in [("MATERIAL",total_material),("FABRICATION",Decimal("1200000")),("FREIGHT",Decimal("180000")),("OVERHEAD",Decimal("420000"))]:
            db.add(CostLine(id=uid(f"cost:{org.id}:{category}"),organization_id=org.id,cost_estimate_id=est.id,category=category,description=f"[DEMO] {category.title()} cost",amount=amount,source={"synthetic_demo":True}))

    # Historical, fictional tender portfolio.  Tenders keep the native model
    # fields; publication/costing dates and comparable market observations are
    # recorded in the existing CostEstimate.context rather than a new schema.
    portfolio = [
        ("TND-DEMO-WH-Q1", "[DEMO] Industrial warehouse structural steel", "[DEMO] Meridian Warehousing", "STRUCTURAL", "Pune (synthetic)", "BEAM", "E250", "45", 290, "ESTIMATING"),
        ("TND-DEMO-PLANT-Q2", "[DEMO] Manufacturing plant expansion", "[DEMO] Axis Components", "INDUSTRIAL", "Nashik (synthetic)", "PLATE", "E250", "38", 205, "SUBMITTED"),
        ("TND-DEMO-INFRA-Q2", "[DEMO] Infrastructure steel supply", "[DEMO] Horizon Works", "BRIDGE", "Nagpur (synthetic)", "CHANNEL", "E250", "52", 175, "WON"),
        ("TND-DEMO-SHED-Q3", "[DEMO] Factory shed construction", "[DEMO] Forgefield Estates", "BUILDING", "Ahmedabad (synthetic)", "BEAM", "E250", "60", 330, "LOST"),
        ("TND-DEMO-FAB-Q3", "[DEMO] Fabrication steel procurement", "[DEMO] Vector Fabrication", "FABRICATION", "Vadodara (synthetic)", "PLATE", "E250", "42", 245, "IN_REVIEW"),
        ("TND-DEMO-COM-Q4", "[DEMO] Commercial building reinforcement", "[DEMO] Northgate Commercial", "BUILDING", "Indore (synthetic)", "CHANNEL", "E250", "36", 190, "ESTIMATING"),
    ]
    for index, (number, title, customer, project_type, location, form, grade, qty, age_days, status) in enumerate(portfolio, start=1):
        costing_date = TODAY - timedelta(days=age_days)
        project, _ = get_or_create(db, Project, organization_id=org.id, code=f"PRJ-{number}", defaults=dict(
            id=uid(f"project:{org.id}:{number}"), name=title, project_type=project_type, location=location,
            estimated_value=Decimal(qty) * Decimal("85000"), status="ACTIVE", start_date=costing_date))
        record, _ = get_or_create(db, Tender, organization_id=org.id, number=number, defaults=dict(
            id=uid(f"tender:{org.id}:{number}"), project_id=project.id, title=title, customer=customer,
            project_type=project_type, location=location, submission_deadline=NOW + timedelta(days=14 + index) if status == "ESTIMATING" else NOW - timedelta(days=max(1, age_days - 14)),
            estimated_value=Decimal(qty) * Decimal("85000"), description=f"Synthetic demo tender. Publication date: {costing_date.isoformat()}. Not discovered from a tender portal.", status=status))
        mat = mats[form]
        boq, _ = get_or_create(db, BOQItem, organization_id=org.id, tender_id=record.id, line_no="1", defaults=dict(
            id=uid(f"boq:{org.id}:{number}"), raw_description=f"[DEMO] {form} {grade}", form=form, grade=grade,
            specification={"synthetic_demo": True}, quantity=Decimal(qty), unit="MT", material_id=mat.id,
            review_status="CONFIRMED", source="MANUAL"))
        get_or_create(db, TenderRequirementSnapshot, organization_id=org.id, tender_id=record.id, source_boq_item_id=boq.id, version=1, defaults=dict(
            id=uid(f"snap:{org.id}:{number}"), material_id=mat.id, form=form, grade=grade, specification={"synthetic_demo":True}, quantity=Decimal(qty), unit="MT", wastage_pct=Decimal("0"), engineering_status="APPROVED", approved_at=NOW, created_at=NOW, updated_at=NOW))
        benchmark = db.scalar(select(PriceObservation).where(PriceObservation.organization_id == org.id, PriceObservation.source_id == src.id,
            PriceObservation.material_form == form, PriceObservation.grade == grade, PriceObservation.region == "West India",
            PriceObservation.currency == "INR", PriceObservation.unit == "MT", PriceObservation.price_basis == "EX_WORKS",
            PriceObservation.observed_on <= costing_date).order_by(PriceObservation.observed_on.desc()))
        context = {"synthetic_demo": True, "costing_reference_date": costing_date.isoformat(), "historical_market_benchmark": None}
        material_cost = Decimal("0")
        if benchmark is not None:
            material_cost = benchmark.price_per_unit * Decimal(qty)
            context["historical_market_benchmark"] = {"observation_id": str(benchmark.id), "observed_on": benchmark.observed_on.isoformat(), "material_form": form, "grade": grade, "region": benchmark.region, "currency": benchmark.currency, "unit": benchmark.unit, "price_basis": benchmark.price_basis, "unit_price": str(benchmark.price_per_unit), "selection_reason": "Latest exact compatible synthetic demonstration observation on or before costing reference date.", "data_age_days": (costing_date - benchmark.observed_on).days}
        estimate, _ = get_or_create(db, CostEstimate, organization_id=org.id, tender_id=record.id, version=1, defaults=dict(
            id=uid(f"estimate:{org.id}:{number}"), context=context, status="DRAFT", material_cost=material_cost,
            freight_cost=Decimal(qty) * Decimal("350"), overhead_cost=Decimal(qty) * Decimal("800"),
            total_cost=material_cost + Decimal(qty) * Decimal("1150"), currency="INR", created_by=admin.id))
        if not db.scalar(select(CostLine).where(CostLine.cost_estimate_id == estimate.id)):
            db.add(CostLine(id=uid(f"cost:{org.id}:{number}:material"), organization_id=org.id, cost_estimate_id=estimate.id, category="MATERIAL", description=f"[DEMO] Historical benchmark reference — {form} {grade}", material_id=mat.id, quantity=Decimal(qty), unit="MT", unit_cost=benchmark.price_per_unit if benchmark else None, amount=material_cost, source=context))
    for index, (kind,title,body,link) in enumerate([("MARKET","[DEMO] Synthetic steel price movement","Synthetic Demo Data: HRC E250 30-day movement.","/market"),("TENDER","[DEMO] New tender opportunity","Seeded demo event: Industrial warehouse structural steel tender.","/tenders"),("TENDER","[DEMO] Tender deadline","Seeded demo event: 200 MT tender submission is due in 7 days.","/tenders"),("PROCUREMENT","[DEMO] Procurement shortage","Synthetic demo tender has 125 MT to source.","/procurement")]):
        get_or_create(db,Notification,organization_id=org.id,title=title,defaults=dict(id=uid(f"note:{org.id}:{kind}:{index}"),user_id=admin.id,kind=kind,body=body,link=link,is_read=False))
    return org


def seed_jayraj_workspace(db) -> Organization:
    """Create an independently scoped, empty customer-onboarding workspace.

    No company registration, inventory, suppliers, tenders, rates, or customer
    relationships are inferred. It receives only the shared steel catalog as
    its own tenant material master.
    """
    org = seed_org(db, key="jayraj-steel", name="JAYRAJ STEEL PRIVATE LIMITED",
                   profiles=["TRADER", "DISTRIBUTOR", "CONTRACTOR"], is_demo=False)
    seed_org_materials(db, org, "JRS")
    return org


def seed_jayraj_training_tenders(db, admin: User, org: Organization,
                                 fixture_key: str = "jayraj-training") -> None:
    """Add reversible, explicitly simulated training opportunities to Jayraj only.

    These records intentionally contain no source URL, supplier quotation, inventory or
    commercial approval.  The first opportunity supplies a reviewable seven-line BOQ
    so the real tender workflow can be demonstrated after a user approves mappings.
    """
    get_or_create(
        db, Customer, organization_id=org.id, code="DEMO-JRS-CUSTOMER",
        defaults=dict(id=uid(f"{fixture_key}:customer"), name="[TRAINING] Warehouse Project Customer",
                      category="SIMULATED TRAINING", credit_terms_days=0, is_active=True, is_demo=True))
    tender_specs = [
        ("DEMO-JRS-WH-001", "[TRAINING TENDER] Structural Steel Supply for Industrial Warehouse", "INDUSTRIAL", "Hyderabad", 8,
         "Fictional training scenario for an industrial warehouse. No government issuer or source document is represented."),
        ("DEMO-JRS-BRG-002", "[TRAINING TENDER] Structural Steel for Access Bridge", "BRIDGE", "Mumbai", 12,
         "Fictional training scenario. Requirements must be uploaded or entered and reviewed before costing."),
        ("DEMO-JRS-FAB-003", "[TRAINING TENDER] Fabricated Steel Platform Package", "FABRICATION", "Chennai", 16,
         "Fictional training scenario. No supplier quotation is attached."),
        ("DEMO-JRS-BLD-004", "[TRAINING TENDER] Pre-Engineered Building Steel Package", "BUILDING", "Delhi NCR", 21,
         "Fictional training scenario. No external tender notice is claimed."),
        ("DEMO-JRS-IND-005", "[TRAINING TENDER] Process Plant Structural Members", "INDUSTRIAL", "Kolkata", 27,
         "Fictional training scenario. Commercial inputs require explicit demo approval."),
        ("DEMO-JRS-RLY-006", "[TRAINING TENDER] Yard Steel Support Works", "RAILWAY", "Hyderabad", 34,
         "Fictional training scenario. Not an authentic railway procurement notice."),
    ]
    for number, title, project_type, location, due_in, description in tender_specs:
        tender, created = get_or_create(
            db, Tender, organization_id=org.id, number=number,
            defaults=dict(id=uid(f"{fixture_key}:tender:{number}"), title=title,
                          customer="Training scenario — no external issuer", project_type=project_type,
                          location=location, submission_deadline=NOW + timedelta(days=due_in),
                          description=description, status="DRAFT", is_demo=True,
                          data_classification="SIMULATED", source_type="TRAINING_SCENARIO",
                          original_source_url=None, publication_date=None,
                          rate_approval_status="DEMO_INPUT_REQUIRED"))
        if not created:
            # Only our deterministic DEMO references are refreshed; genuine Jayraj rows are untouched.
            tender.title = title
            tender.customer = "Training scenario — no external issuer"
            tender.description = description
            tender.is_demo = True
            tender.data_classification = "SIMULATED"
            tender.source_type = "TRAINING_SCENARIO"
            tender.rate_approval_status = "DEMO_INPUT_REQUIRED"

    training_materials = [
        ("BEAM", "E250", "IS 2062", "ISMB 300", "MT", "[TRAINING] ISMB 300 Beam E250"),
        ("CHANNEL", "E250", "IS 2062", "ISMC 200", "MT", "[TRAINING] ISMC 200 Channel E250"),
        ("ANGLE", "E250", "IS 2062", "ISA 75x75x6", "MT", "[TRAINING] ISA 75x75x6 Angle E250"),
        ("PLATE", "E250", "IS 2062", "10 mm", "MT", "[TRAINING] MS Plate 10 mm E250"),
        ("GI_SHEET", "Z120", "IS 277", "Z120 coating", "SQM", "[TRAINING] GI Sheet IS 277 Z120"),
        ("REBAR", "FE500D", "IS 1786", "12 mm", "MT", "[TRAINING] TMT Fe 500D 12 mm"),
        ("REBAR", "FE550D", "IS 1786", "16 mm", "MT", "[TRAINING] TMT Fe 550D 16 mm"),
    ]
    materials: dict[str, OrganizationMaterial] = {}
    for index, (form, grade, standard, dimensions, unit, name) in enumerate(training_materials, 1):
        sku = f"JRS-TRAIN-{index:02d}"
        material, _ = get_or_create(
            db, OrganizationMaterial, organization_id=org.id, sku=sku,
            defaults=dict(id=uid(f"{fixture_key}:material:{sku}"), name=name, form=form,
                          grade=grade, standard=standard, base_unit=unit,
                          specification={"dimensions": dimensions, "data_classification": "SIMULATED",
                                         "usage": "Training tender mapping only"}, is_active=True))
        materials[sku] = material

    # Dedicated simulated warehouse: training stock never alters an operational Jayraj lot.
    training_wh, _ = get_or_create(db, Warehouse, organization_id=org.id, code="JRS-TRAINING",
        defaults=dict(id=uid(f"{fixture_key}:warehouse"), name="[TRAINING] Tender Demo Warehouse",
                      location="Simulated training location", is_active=True))
    training_stock = [("JRS-TRAIN-01", "10", "MT", "28000"), ("JRS-TRAIN-02", "5", "MT", "27500"),
        ("JRS-TRAIN-03", "3", "MT", "29000"), ("JRS-TRAIN-04", "6", "MT", "31000"),
        ("JRS-TRAIN-05", "1500", "SQM", "650"), ("JRS-TRAIN-06", "4", "MT", "42000"),
        ("JRS-TRAIN-07", "2", "MT", "43000")]
    for sku, quantity, unit, unit_cost in training_stock:
        lot, created = get_or_create(db, StockLot, organization_id=org.id, material_id=materials[sku].id,
            warehouse_id=training_wh.id, lot_number=f"TRAINING-{sku}", defaults=dict(
                id=uid(f"{fixture_key}:lot:{sku}"), heat_number="SIMULATED", quality_status="OK",
                on_hand_qty=Decimal(quantity), reserved_qty=Decimal("0"), unit=unit, unit_cost=Decimal(unit_cost),
                source={"classification":"TRAINING","simulated":True,"reference":"JRS-TRAINING-RECEIPT"}))
        if created:
            db.add(InventoryMovement(id=uid(f"{fixture_key}:receipt:{sku}"), organization_id=org.id,
                material_id=materials[sku].id, warehouse_id=training_wh.id, stock_lot_id=lot.id,
                movement_type="RECEIPT", quantity=Decimal(quantity), unit=unit,
                balance_after_on_hand=Decimal(quantity), reference={"classification":"TRAINING","simulated":True},
                idempotency_key=f"seed:{fixture_key}:receipt:{sku}"))

    warehouse = db.scalar(select(Tender).where(Tender.organization_id == org.id,
                                                Tender.number == "DEMO-JRS-WH-001"))
    assert warehouse is not None
    lines = [
        ("ST-01", "ISMB 300 E250 structural beams, IS 2062", "BEAM", "E250", "JRS-TRAIN-01", "24", "MT", "ISMB 300"),
        ("ST-02", "ISMC 200 E250 structural channels, IS 2062", "CHANNEL", "E250", "JRS-TRAIN-02", "12", "MT", "ISMC 200"),
        ("ST-03", "ISA 75x75x6 E250 structural angles, IS 2062", "ANGLE", "E250", "JRS-TRAIN-03", "8", "MT", "ISA 75x75x6"),
        ("ST-04", "MS Plate 10 mm E250, IS 2062", "PLATE", "E250", "JRS-TRAIN-04", "16", "MT", "10 mm"),
        ("ST-05", "GI Sheet Z120, IS 277", "GI_SHEET", "Z120", "JRS-TRAIN-05", "4200", "SQM", "Z120 coating"),
        ("ST-06", "TMT Fe 500D 12 mm, IS 1786", "REBAR", "FE500D", "JRS-TRAIN-06", "10", "MT", "12 mm"),
        ("ST-07", "TMT Fe 550D 16 mm, IS 1786", "REBAR", "FE550D", "JRS-TRAIN-07", "6", "MT", "16 mm"),
    ]
    for line_no, raw, form, grade, sku, quantity, unit, dimensions in lines:
        get_or_create(
            db, BOQItem, tender_id=warehouse.id, organization_id=org.id, line_no=line_no,
            defaults=dict(id=uid(f"{fixture_key}:boq:{line_no}"), raw_description=raw, form=form, grade=grade,
                          specification={"standard": next(m.standard for key, m in materials.items() if key == sku),
                                         "dimensions": dimensions, "data_classification": "SIMULATED"},
                          quantity=Decimal(quantity), unit=unit, material_id=materials[sku].id,
                          review_status="PENDING", source="MANUAL",
                          page_ref="SIMULATED TRAINING SCHEDULE"))


def seed_pib_october_release(db) -> None:
    """Idempotently store the official PIB/JPC Jul-Sep 2026 four-metro series."""
    url = "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2319469&lang=2&reg=48"
    source, _ = get_or_create(db, MarketSource, name="Ministry of Steel / PIB — JPC steel prices", organization_id=None,
        defaults=dict(id=uid("market-source:pib:2319469"), provenance_classification="OFFICIAL_REFERENCE", reference_url=url,
        attribution_text="Ministry of Steel / Press Information Bureau; provisional JPC data.", license_status="APPROVED", visibility="GLOBAL", redistribution_permitted=True))
    checksum = sha256(url.encode()).hexdigest()
    document, _ = get_or_create(db, MarketSourceDocument, source_id=source.id, sha256_checksum=checksum,
        defaults=dict(id=uid("market-document:pib:2319469"), original_document_url=url, publisher="Ministry of Steel / Press Information Bureau", document_title="India's Steel Sector Posts Steady Growth in H1 FY 2026–27", published_at=datetime(2026,10,6,tzinfo=timezone.utc), reporting_period="Jul-Sep 2026", retrieved_at=datetime.now(timezone.utc), extraction_status="EXTRACTED", reuse_basis="Official public PIB release; URL retained as source evidence."))
    price_source, _ = get_or_create(db, PriceSource, organization_id=None, name="Ministry of Steel / PIB (official reference)", defaults=dict(id=uid("price-source:pib:2319469"), source_type="PROVIDER", provider_key="pib-jpc-2319469", is_synthetic=False))
    rows = [("TMT","", "10 mm", [56698,58002,65298]), ("HRC","", "2 mm", [69828,70448,76085]), ("CRC","", "0.63 mm", [76582,76462,84972]), ("GP_SHEET","", "0.63 mm", [86415,86668,94148])]
    for form, grade, dimension, values in rows:
        for month, value in zip((7,8,9), values):
            observed = date(2026, month, 1)
            get_or_create(db, PriceObservation, external_observation_id=f"pib-2319469-{form}-{month}", defaults=dict(id=uid(f"pib-2319469:{form}:{month}"), organization_id=None, source_id=price_source.id, source_document_id=document.id, material_form=form, grade=grade, region="India four-metro average", dimension_note=f"{dimension}; GST included; national four-metro average", price_basis="RETAIL_GST_INCLUDED", price_per_unit=Decimal(value), unit="MT", currency="INR", observed_on=observed, is_synthetic=False))


def run_seed() -> dict:
    if not settings.demo_mode:
        raise SystemExit("Refusing to seed demo data: DEMO_MODE=false (production safety).")
    db = SessionLocal()
    summary = {}
    try:
        seed_catalog(db)
        seed_prices(db)
        seed_pib_october_release(db)

        orgs = {}
        orgs["apex"] = seed_org(db, key="apex", name="[DEMO] Apex Steel Traders Pvt Ltd",
                                profiles=["TRADER", "DISTRIBUTOR"])
        orgs["metro"] = seed_org(db, key="metro", name="[DEMO] Metro Steel Distributors Pvt Ltd",
                                 profiles=["DISTRIBUTOR", "TRADER"])
        orgs["precision"] = seed_org(db, key="precision",
                                     name="[DEMO] PrecisionSteel Fabricators Pvt Ltd",
                                     profiles=["FABRICATOR", "TRADER"])
        orgs["railbuild"] = seed_org(db, key="railbuild",
                                     name="[DEMO] RailBuild Infrastructure Pvt Ltd",
                                     profiles=["CONTRACTOR", "TRADER"])
        orgs["market_showcase"] = seed_org(db, key="market-showcase",
                                            name="[DEMO] SteelBid Market Showcase",
                                            profiles=["CONTRACTOR", "TRADER"])
        orgs["jayraj"] = seed_jayraj_workspace(db)

        # Shared super-demo user (member of all four orgs) for org-switching demo
        seed_user(db, settings.demo_admin_email, "Demo Admin (all companies)",
                  [(o, "ADMIN") for o in orgs.values()])
        # Role-specific users in the primary org
        apex = orgs["apex"]
        roles = {"sales@apex.demo": "SALES", "procurement@apex.demo": "PROCUREMENT",
                 "inventory@apex.demo": "INVENTORY", "fabrication@apex.demo": "FABRICATION",
                 "finance@apex.demo": "FINANCE", "estimator@apex.demo": "ESTIMATOR",
                 "viewer@apex.demo": "VIEWER"}
        for email, role in roles.items():
            seed_user(db, email, f"Demo {role.title()} — Apex", [(apex, role)])
        admins = {}
        for key, email in (("apex", "admin@apex.demo"), ("metro", "admin@metro.demo"),
                           ("precision", "admin@precision.demo"),
                           ("railbuild", "admin@railbuild.demo"),
                           ("market_showcase", "admin@showcase.demo"),
                           ("jayraj", "admin@jayraj.demo")):
            admins[key] = seed_user(db, email, f"Demo Admin — {key.title()}",
                                    [(orgs[key], "ADMIN")])
        db.commit()

        # Re-open: rich seeds use their own lookups and commit at the end
        seed_apex_trader(db, admins["apex"])
        seed_metro_distributor(db, admins["metro"])
        seed_precision_fabricator(db, admins["precision"])
        seed_railbuild_contractor(db, admins["railbuild"])
        seed_market_showcase(db, admins["market_showcase"])
        seed_jayraj_training_tenders(db, admins["jayraj"], orgs["jayraj"])
        db.commit()

        from sqlalchemy import func
        summary = {
            "organizations": db.scalar(select(func.count()).select_from(Organization)),
            "users": db.scalar(select(func.count()).select_from(User)),
        }
        print(f"Seed complete (idempotent). Orgs={summary['organizations']} Users={summary['users']}")
        print(DEMO_PASSWORD_NOTE)
    finally:
        db.close()
    return summary


if __name__ == "__main__":
    run_seed()
