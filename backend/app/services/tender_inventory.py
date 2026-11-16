"""Tender BOM inventory eligibility.

This is intentionally stricter than a portfolio inventory total.  A tender
requirement is never satisfied by a different unit or by training-only stock
when the tender is operational.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calc.finance import ZERO, q_qty
from app.models.fabrication import BOMItem
from app.models.inventory import StockLot
from app.models.materials import OrganizationMaterial
from app.models.projects import Tender, TenderRequirementSnapshot


def unit_safe_inventory_breakdown(lots: list[StockLot], allocations: list[object]) -> dict[str, dict[str, Decimal]]:
    """Return portfolio stock facts without ever crossing unit boundaries.

    ``StockLot.reserved_qty`` remains the ledger source of truth for reserved
    stock.  Tender allocations are reported separately from active persisted
    allocation records; they are deliberately not subtracted a second time.
    The function accepts allocation-like objects to keep it usable from the
    dashboard without introducing another inventory rules engine.
    """
    totals: dict[str, dict[str, Decimal]] = {}
    for lot in lots:
        values = totals.setdefault(lot.unit, {
            "on_hand": ZERO, "eligible": ZERO, "reserved": ZERO,
            "quality_held": ZERO, "allocated": ZERO, "available": ZERO,
        })
        on_hand = Decimal(str(lot.on_hand_qty))
        reserved = Decimal(str(lot.reserved_qty))
        values["on_hand"] += on_hand
        if lot.quality_status == "OK":
            values["eligible"] += on_hand
            values["reserved"] += reserved
            values["available"] += max(ZERO, on_hand - reserved)
        else:
            # Held/rejected quantities are physical stock, never eligible.
            values["quality_held"] += on_hand
    for allocation in allocations:
        if getattr(allocation, "status", None) != "ACTIVE":
            continue
        unit = getattr(allocation, "unit", None)
        if not unit:
            continue
        values = totals.setdefault(unit, {
            "on_hand": ZERO, "eligible": ZERO, "reserved": ZERO,
            "quality_held": ZERO, "allocated": ZERO, "available": ZERO,
        })
        values["allocated"] += Decimal(str(allocation.quantity))
    return totals


def is_training_tender(tender: Tender) -> bool:
    return bool(tender.is_demo) or (tender.data_classification or "").upper() in {"TRAINING", "SIMULATED"}


def _is_training_lot(lot: StockLot) -> bool:
    source = lot.source or {}
    return str(source.get("classification", source.get("data_classification", ""))).upper() in {"TRAINING", "SIMULATED"}


def mapping_compatibility(material: OrganizationMaterial, requirement: TenderRequirementSnapshot | object) -> list[str]:
    """Return incompatibility reasons; no implicit grade/spec/unit conversion."""
    reasons: list[str] = []
    for field in ("form", "grade"):
        required = getattr(requirement, field, None)
        actual = getattr(material, field, None)
        if required and actual and str(required).upper() != str(actual).upper():
            reasons.append(f"{field} mismatch ({required} vs {actual})")
    required_unit = getattr(requirement, "unit", None)
    if required_unit and material.base_unit != required_unit:
        reasons.append(f"unit mismatch ({required_unit} vs {material.base_unit}); no conversion is approved")
    specification = getattr(requirement, "specification", None) or {}
    required_standard = specification.get("standard")
    if required_standard and material.standard and str(required_standard).upper() != str(material.standard).upper():
        reasons.append(f"standard mismatch ({required_standard} vs {material.standard})")
    required_dimensions = specification.get("dimensions") or specification.get("size")
    actual_dimensions = (material.specification or {}).get("dimensions") or (material.specification or {}).get("size")
    if required_dimensions and actual_dimensions and str(required_dimensions).upper() != str(actual_dimensions).upper():
        reasons.append("dimensions mismatch")
    return reasons


def analyze_bom_item_inventory(db: Session, org_id, tender: Tender, item: BOMItem) -> dict:
    material = db.get(OrganizationMaterial, item.material_id)
    if material is None or material.organization_id != org_id:
        return {"eligible_quantity": ZERO, "shortage_quantity": item.quantity, "status": "BLOCKED", "reasons": ["mapped material is unavailable"]}
    snapshot = db.get(TenderRequirementSnapshot, item.tender_requirement_snapshot_id) if item.tender_requirement_snapshot_id else None
    reasons = mapping_compatibility(material, snapshot) if snapshot else []
    if item.unit != material.base_unit:
        reasons.append(f"BOM unit mismatch ({item.unit} vs {material.base_unit}); no conversion is approved")
    if snapshot and item.unit != snapshot.unit:
        reasons.append(f"BOM unit differs from approved requirement ({item.unit} vs {snapshot.unit})")
    if reasons:
        return {"eligible_quantity": ZERO, "shortage_quantity": item.quantity, "status": "BLOCKED", "reasons": reasons}

    eligible = ZERO
    excluded_training = ZERO
    excluded_incompatible_unit = ZERO
    for lot in db.scalars(select(StockLot).where(
        StockLot.organization_id == org_id, StockLot.material_id == item.material_id,
        StockLot.quality_status == "OK")).all():
        available = max(ZERO, Decimal(str(lot.on_hand_qty)) - Decimal(str(lot.reserved_qty)))
        if lot.unit != item.unit:
            excluded_incompatible_unit += available
        elif not is_training_tender(tender) and _is_training_lot(lot):
            excluded_training += available
        else:
            eligible += available
    shortage = max(ZERO, Decimal(str(item.quantity)) - eligible)
    notes: list[str] = []
    if excluded_training:
        notes.append("training-only stock excluded")
    if excluded_incompatible_unit:
        notes.append("incompatible-unit stock excluded")
    return {"eligible_quantity": q_qty(eligible), "shortage_quantity": q_qty(shortage),
            "status": "READY" if not shortage else "SHORTAGE", "reasons": notes,
            "excluded_training_quantity": q_qty(excluded_training),
            "excluded_incompatible_unit_quantity": q_qty(excluded_incompatible_unit)}
