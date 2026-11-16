from decimal import Decimal as D

from app.calc.finance import tender_commercials


def test_tender_commercials_distinguishes_markup_from_margin_with_decimal_precision():
    markup = tender_commercials(D("100.0000"), markup=D("0.25"))
    assert markup["proposed_pre_tax_bid"] == D("125.0000")
    assert markup["projected_profit"] == D("25.0000")
    assert markup["markup"] == D("0.250000")
    assert markup["gross_margin"] == D("0.200000")
    margin = tender_commercials(D("100.0000"), target_margin=D("0.2"))
    assert margin["proposed_pre_tax_bid"] == D("125.0000")


def test_tender_commercials_requires_one_explicit_pricing_input():
    try:
        tender_commercials(D("100"))
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("missing commercial input was accepted")
