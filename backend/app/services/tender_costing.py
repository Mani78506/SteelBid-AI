"""Tender supplier compatibility and landed-cost calculations (Decimal only)."""
from datetime import date
from decimal import Decimal

from app.calc.finance import ZERO, landed_unit_cost, q_money, shortage_qty


def compatible_offer(requirement, material, quote, quote_material, eligible_qty: Decimal) -> dict:
    reasons: list[str] = []
    if quote.status != "OPEN": reasons.append("quote is not open")
    if quote.valid_until and quote.valid_until < date.today(): reasons.append("quote has expired")
    if quote.material_id != requirement.material_id: reasons.append("material identity differs")
    if quote.unit != requirement.unit: reasons.append("unsupported unit conversion")
    if quote_material.form != requirement.form or quote_material.grade != requirement.grade: reasons.append("form or grade differs")
    if requirement.specification and quote_material.specification != requirement.specification: reasons.append("specification differs or is not confirmed")
    if quote.quantity <= ZERO: reasons.append("quoted quantity is not positive")
    landed = landed_unit_cost(quote.unit_price, quote.fx_rate_to_org_ccy, quote.freight_per_unit,
                              quote.duty_pct, quote.tax_pct, quote.tax_recoverable)
    required = requirement.quantity * (Decimal("1") + requirement.wastage_pct)
    shortage = shortage_qty(required, eligible_qty)
    return {"compatible": not reasons, "reasons": reasons, "required_qty": required,
            "eligible_qty": eligible_qty, "shortage_qty": shortage, "landed_cost_per_unit": landed}
