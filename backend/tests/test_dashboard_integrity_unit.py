"""Database-free Phase 4A dashboard integrity tests.

These deliberately use no project pytest fixtures, migrations, seeds, or
database connection.  They cover the arithmetic boundary shared by the
enhanced dashboard and leave tenant/offer persistence to the existing
tenant-scoped API contract suites.
"""
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.ops import EnhancedDashboardSummary
from app.services.tender_inventory import mapping_compatibility, unit_safe_inventory_breakdown


def _lot(*, unit: str, on_hand: str, reserved: str = "0", quality: str = "OK"):
    return SimpleNamespace(unit=unit, on_hand_qty=Decimal(on_hand), reserved_qty=Decimal(reserved), quality_status=quality)


def _allocation(*, unit: str, quantity: str, status: str = "ACTIVE"):
    return SimpleNamespace(unit=unit, quantity=Decimal(quantity), status=status)


def test_inventory_breakdown_keeps_mt_sqm_and_pieces_separate_with_decimal_precision():
    totals = unit_safe_inventory_breakdown([
        _lot(unit="MT", on_hand="10.125000", reserved="1.125000"),
        _lot(unit="SQM", on_hand="32.500000", reserved="2.250000"),
        _lot(unit="PCS", on_hand="9", reserved="3"),
    ], [_allocation(unit="MT", quantity="1.125000"), _allocation(unit="PCS", quantity="2")])

    assert totals["MT"]["available"] == Decimal("9.000000")
    assert totals["SQM"]["available"] == Decimal("30.250000")
    assert totals["PCS"]["available"] == Decimal("6")
    assert set(totals) == {"MT", "SQM", "PCS"}


def test_inventory_breakdown_excludes_quality_held_and_does_not_double_count_allocations():
    totals = unit_safe_inventory_breakdown([
        _lot(unit="MT", on_hand="10", reserved="4"),
        _lot(unit="MT", on_hand="3", quality="QUARANTINED"),
        _lot(unit="MT", on_hand="2", quality="REJECTED"),
    ], [_allocation(unit="MT", quantity="2"), _allocation(unit="MT", quantity="1", status="RELEASED")])

    assert totals["MT"] == {
        "on_hand": Decimal("15"), "eligible": Decimal("10"), "reserved": Decimal("4"),
        "quality_held": Decimal("5"), "allocated": Decimal("2"), "available": Decimal("6"),
    }


def test_material_mapping_rejects_grade_specification_and_unit_mismatch():
    material = SimpleNamespace(form="CHANNEL", grade="E250", base_unit="MT", standard="IS 808", specification={"dimensions": "150"})
    requirement = SimpleNamespace(form="CHANNEL", grade="E350", unit="SQM", specification={"standard": "IS 2062", "dimensions": "200"})
    reasons = mapping_compatibility(material, requirement)

    assert any("grade mismatch" in reason for reason in reasons)
    assert any("unit mismatch" in reason for reason in reasons)
    assert any("standard mismatch" in reason for reason in reasons)
    assert "dimensions mismatch" in reasons


def test_material_mapping_accepts_extracted_dimension_tokens_only_when_they_match():
    material = SimpleNamespace(form="BEAM", grade="E250", base_unit="MT", standard="IS 2062", specification={"dimensions": "300 mm"})
    matching = SimpleNamespace(form="BEAM", grade="E250", unit="MT", specification={"standard": "IS 2062", "dimensions": ["300 mm"]})
    mismatched = SimpleNamespace(form="BEAM", grade="E250", unit="MT", specification={"standard": "IS 2062", "dimensions": ["200 mm"]})

    assert mapping_compatibility(material, matching) == []
    assert "dimensions mismatch" in mapping_compatibility(material, mismatched)


def test_enhanced_contract_accepts_null_unavailable_financials_without_zero_substitution():
    payload = {
        "organization": {}, "kpis": {}, "priorities": [], "recent_inquiries": [],
        "procurement_shortages": [], "price_observations": [], "upcoming_dispatches": [],
        "production_status": [], "tender_deadlines": [], "recent_activity": [],
        "market_trends": [], "market_comparisons": [], "scenario_summary": {}, "new_tenders": [],
        "tender_pipeline": {}, "tender_amendments": [], "boq_review_status": {}, "bom_readiness": [],
        "tender_shortages": [],
        "inventory_breakdown": {"unit": None, "on_hand": None, "eligible": None, "reserved": None,
                                "quality_held": None, "allocated": None, "available": None, "unit_totals": []},
        "atp_by_material": [], "active_costing_quotes": [], "margin_exposure": {}, "pricing_scenarios": {},
        "open_rfqs": {}, "pending_quotes": {}, "procurement_requirements": [],
        "tender_financials": [{"tender_id": "t", "tender_number": "T-1", "official_estimated_value": None,
                                "currency": "INR", "estimate_status": "UNAVAILABLE", "estimate_id": None,
                                "estimate_total": None, "commercial_approval_status": None, "estimate_source": None}],
        "delivery_risks": [], "approval_queue": [], "price_alerts": {},
    }
    result = EnhancedDashboardSummary.model_validate(payload)
    assert result.tender_financials[0].estimate_total is None
    assert result.inventory_breakdown.on_hand is None
