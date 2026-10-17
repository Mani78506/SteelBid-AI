"""Seed runner. Usage: python -m app.seed.run

Idempotent: safe to run repeatedly. Refuses to run when DEMO_MODE=false (production).
All demo data is visibly fictional: [DEMO] prefixes, is_demo flags, labeled synthetic prices.
"""
from datetime import timedelta
from decimal import Decimal

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
from app.models.inventory import Reservation
from app.models.ops import Dispatch, DispatchItem, Invoice, Payment
from app.models.projects import BOQItem, Project, ProjectRequirement, Tender
from app.seed.demo import (CATALOG, NOW, TODAY, get_or_create, seed_catalog, seed_customers,
                           seed_lots, seed_org_materials, seed_prices, seed_quotation_chain,
                           seed_suppliers, seed_warehouses, uid)

settings = get_settings()
DEMO_PASSWORD_NOTE = "Demo passwords come from DEMO_ADMIN_PASSWORD env (default in .env.example)."


def _password() -> str:
    return settings.demo_admin_password


def seed_org(db, *, key: str, name: str, profiles: list[str]):
    org, _ = get_or_create(db, Organization, name=name,
                           defaults=dict(id=uid(f"org:{key}"), business_profiles=profiles,
                                         currency_code="INR", timezone="Asia/Kolkata",
                                         is_demo=True))
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


def run_seed() -> dict:
    if not settings.demo_mode:
        raise SystemExit("Refusing to seed demo data: DEMO_MODE=false (production safety).")
    db = SessionLocal()
    summary = {}
    try:
        seed_catalog(db)
        seed_prices(db)

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
                           ("railbuild", "admin@railbuild.demo")):
            admins[key] = seed_user(db, email, f"Demo Admin — {key.title()}",
                                    [(orgs[key], "ADMIN")])
        db.commit()

        # Re-open: rich seeds use their own lookups and commit at the end
        seed_apex_trader(db, admins["apex"])
        seed_metro_distributor(db, admins["metro"])
        seed_precision_fabricator(db, admins["precision"])
        seed_railbuild_contractor(db, admins["railbuild"])
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
