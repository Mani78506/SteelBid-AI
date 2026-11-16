"""Provision the single, isolated public Jayraj training sandbox.

This is deliberately not part of application startup or the general demo seed.
It is idempotent and creates only records with explicit DEMO/TRAINING labels.
Run with ``python scripts/provision_jayraj_public_demo.py --confirm``.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal

from app.config import get_settings
from app.database import SessionLocal
from app.models.crm import Customer
from app.models.projects import BOQItem, Tender
from app.seed.demo import get_or_create, uid
from app.seed.run import NOW, seed_jayraj_training_tenders, seed_org, seed_org_materials, seed_user

SANDBOX_NAME = "[DEMO] JAYRAJ STEEL PRIVATE LIMITED — TRAINING WORKSPACE"
VIEWER_EMAIL = "viewer@jayraj-demo.public"


def main() -> int:
    if "--confirm" not in sys.argv:
        raise SystemExit("Refused: rerun with --confirm to provision the labelled public demo sandbox")
    settings = get_settings()
    if not settings.is_production or not settings.public_demo_enabled:
        raise SystemExit("Refused: requires production with PUBLIC_DEMO_ENABLED=true")
    if settings.public_demo_viewer_email.lower() != VIEWER_EMAIL:
        raise SystemExit("Refused: PUBLIC_DEMO_VIEWER_EMAIL must target the sandbox viewer")

    db = SessionLocal()
    try:
        org = seed_org(db, key="jayraj-public-demo", name=SANDBOX_NAME,
                       profiles=["TRADER", "DISTRIBUTOR", "CONTRACTOR"], is_demo=True)
        viewer = seed_user(db, VIEWER_EMAIL, "Public Demo Viewer — Jayraj Training", [(org, "VIEWER")])
        seed_org_materials(db, org, "JRS-DEMO")
        # Reuse the local Jayraj training fixture with a sandbox-specific key so
        # every UUID and inventory movement remains separate from real Jayraj.
        seed_jayraj_training_tenders(db, viewer, org, fixture_key="jayraj-public-demo")
        customer, _ = get_or_create(db, Customer, organization_id=org.id, code="JRS-DEMO-CUSTOMER",
            defaults={"id": uid("jayraj-public-demo:customer"), "name": "[DEMO] Industrial Warehouse Customer",
                      "category": "SIMULATED TRAINING", "credit_terms_days": 0, "is_active": True, "is_demo": True})
        tender, _ = get_or_create(db, Tender, organization_id=org.id, number="DEMO-JRS-PUBLIC-001",
            defaults={"id": uid("jayraj-public-demo:tender"), "title": "[DEMO] Jayraj Structural Steel Training Tender",
                      "customer": customer.name, "project_type": "INDUSTRIAL", "location": "Simulated workspace",
                      "submission_deadline": NOW + timedelta(days=14), "status": "DRAFT", "is_demo": True,
                      "data_classification": "SIMULATED", "source_type": "TRAINING_SCENARIO",
                      "description": "Fictional public training scenario; not a live opportunity."})
        lines = [("1", "[DEMO] ISMB 300 Beam E250, IS 2062", "BEAM", "E250", "24", "MT"),
                 ("2", "[DEMO] ISMC 200 Channel E250, IS 2062", "CHANNEL", "E250", "12", "MT"),
                 ("3", "[DEMO] GI Sheet Z120, IS 277", "GI_SHEET", "Z120", "4200", "SQM")]
        for line_no, description, form, grade, quantity, unit in lines:
            get_or_create(db, BOQItem, tender_id=tender.id, organization_id=org.id, line_no=line_no,
                defaults={"id": uid(f"jayraj-public-demo:boq:{line_no}"), "raw_description": description,
                          "form": form, "grade": grade, "quantity": Decimal(quantity), "unit": unit,
                          "review_status": "PENDING", "source": "MANUAL",
                          "specification": {"data_classification": "SIMULATED", "note": "Public training data"}})
        db.commit()
        print(f"Public demo sandbox ready: organization={org.name} viewer={viewer.email} tender={tender.number}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
