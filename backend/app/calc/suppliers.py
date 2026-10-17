"""Supplier offer comparison — normalize by landed cost, lead time, validity."""
from dataclasses import dataclass
from decimal import Decimal

from app.calc.finance import landed_unit_cost, q_money


@dataclass
class Offer:
    supplier_id: str
    supplier_name: str
    unit_price: Decimal
    fx_rate: Decimal
    freight_per_unit: Decimal
    duty_pct: Decimal
    tax_pct: Decimal
    tax_recoverable: bool
    lead_time_days: int
    payment_terms_days: int
    valid: bool

    @property
    def landed_cost(self) -> Decimal:
        return landed_unit_cost(
            self.unit_price, self.fx_rate, self.freight_per_unit,
            self.duty_pct, self.tax_pct, self.tax_recoverable)


def rank_offers(offers: list[Offer], max_lead_time_days: int | None = None) -> list[dict]:
    """Rank valid offers by landed cost (exact Decimal). Excludes invalid/expired offers.
    Offers exceeding max_lead_time_days are demoted below compliant offers."""
    rows = []
    for o in offers:
        if not o.valid:
            continue
        lead_ok = max_lead_time_days is None or o.lead_time_days <= max_lead_time_days
        rows.append({
            "supplier_id": o.supplier_id,
            "supplier_name": o.supplier_name,
            "unit_price": q_money(o.unit_price * o.fx_rate),
            "landed_cost": o.landed_cost,
            "lead_time_days": o.lead_time_days,
            "payment_terms_days": o.payment_terms_days,
            "lead_time_ok": lead_ok,
        })
    rows.sort(key=lambda r: (not r["lead_time_ok"], r["landed_cost"], r["lead_time_days"]))
    if rows:
        best = rows[0]["landed_cost"]
        for i, r in enumerate(rows):
            r["rank"] = i + 1 if r["lead_time_ok"] else None
            r["premium_vs_best"] = q_money(r["landed_cost"] - best)
    return rows
