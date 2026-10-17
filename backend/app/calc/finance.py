"""Deterministic financial arithmetic. Money/quantity math ONLY here — never in routers, never in AI.

All functions use Python Decimal. Quantization: money 4dp, quantity 6dp, ratio 6dp.
"""
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
MONEY_Q = D("0.0001")
QTY_Q = D("0.000001")
RATIO_Q = D("0.000001")
ZERO = D("0")


def q_money(v: Decimal) -> Decimal:
    return v.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def q_qty(v: Decimal) -> Decimal:
    return v.quantize(QTY_Q, rounding=ROUND_HALF_UP)


def q_ratio(v: Decimal) -> Decimal:
    return v.quantize(RATIO_Q, rounding=ROUND_HALF_UP)


def available_qty(on_hand: Decimal, reserved: Decimal, quality_held: Decimal = ZERO) -> Decimal:
    """Available = On-hand − Reserved − Quality-held. Never negative."""
    return max(ZERO, q_qty(on_hand - reserved - quality_held))


def shortage_qty(gross_requirement: Decimal, eligible_available: Decimal,
                 approved_incoming: Decimal = ZERO) -> Decimal:
    """Shortage = max(0, Gross requirement − Eligible available − Approved incoming)."""
    return max(ZERO, q_qty(gross_requirement - eligible_available - approved_incoming))


def gross_margin(selling_price: Decimal, estimated_cost: Decimal) -> Decimal:
    """Gross margin = (Selling price − Estimated cost) / Selling price. 0 if price is 0."""
    if selling_price == 0:
        return ZERO
    return q_ratio((selling_price - estimated_cost) / selling_price)


def selling_from_margin(estimated_cost: Decimal, target_margin: Decimal) -> Decimal:
    """Selling price = Estimated cost / (1 − Target margin).
    Margin is expressed as a fraction of selling price (NOT markup)."""
    if target_margin >= D("1"):
        raise ValueError("Target margin must be < 100% for margin-based pricing")
    return q_money(estimated_cost / (D("1") - target_margin))


def markup_to_margin(markup: Decimal) -> Decimal:
    """Convert markup-on-cost to margin-on-price: margin = markup / (1 + markup)."""
    return q_ratio(markup / (D("1") + markup))


def cost_estimate_total(material: Decimal = ZERO, fabrication: Decimal = ZERO, labour: Decimal = ZERO,
                        freight: Decimal = ZERO, installation: Decimal = ZERO,
                        subcontracting: Decimal = ZERO, overhead: Decimal = ZERO,
                        contingency_pct: Decimal = ZERO) -> tuple[Decimal, Decimal]:
    """Estimated cost = Material + Fabrication + Labour + Freight + Installation
       + Subcontracting + Overhead + Contingency.
    Returns (subtotal_before_contingency, total_with_contingency)."""
    subtotal = material + fabrication + labour + freight + installation + subcontracting + overhead
    contingency = q_money(subtotal * contingency_pct)
    return q_money(subtotal), q_money(subtotal + contingency)


def landed_unit_cost(unit_price: Decimal, fx_rate: Decimal, freight_per_unit: Decimal = ZERO,
                     duty_pct: Decimal = ZERO, tax_pct: Decimal = ZERO,
                     tax_recoverable: bool = True) -> Decimal:
    """Normalized landed cost per unit:
    base = unit_price * fx; duties always a cost; taxes only a cost when NOT recoverable."""
    base = unit_price * fx_rate
    duty = base * duty_pct
    tax = D("0") if tax_recoverable else base * tax_pct
    return q_money(base + duty + tax + freight_per_unit)


def weighted_average_cost(lots: list[tuple[Decimal, Decimal]]) -> Decimal:
    """lots = [(qty, unit_cost), ...] → weighted average unit cost (0 for empty/zero qty)."""
    total_qty = sum((q for q, _ in lots), ZERO)
    if total_qty <= 0:
        return ZERO
    return q_money(sum((q * c for q, c in lots), ZERO) / total_qty)


def inventory_valuation(lots: list[tuple[Decimal, Decimal]]) -> Decimal:
    """Sum of on_hand * unit_cost."""
    return q_money(sum((q * c for q, c in lots), ZERO))
