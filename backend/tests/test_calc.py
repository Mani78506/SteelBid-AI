"""Unit tests for deterministic calculation services (Part J rules)."""
from decimal import Decimal as D
import pytest

from app.calc.finance import (available_qty, cost_estimate_total, gross_margin,
                              inventory_valuation, landed_unit_cost, markup_to_margin,
                              selling_from_margin, shortage_qty, weighted_average_cost)


class TestAvailability:
    def test_available_never_negative(self):
        assert available_qty(D("40"), D("55")) == D("0")
        assert available_qty(D("55"), D("40")) == D("15")

    def test_available_minus_quality_held(self):
        assert available_qty(D("55"), D("10"), D("15")) == D("30")

    def test_shortage(self):
        assert shortage_qty(D("100"), D("40")) == D("60")
        assert shortage_qty(D("100"), D("40"), D("60")) == D("0")
        assert shortage_qty(D("10"), D("40")) == D("0")


class TestMargin:
    def test_gross_margin(self):
        # (6386.36 - 5620) / 6386.36 ≈ 0.12
        price = selling_from_margin(D("5620"), D("0.12"))
        assert gross_margin(price, D("5620")) == D("0.120000")

    def test_selling_from_margin_exact(self):
        assert selling_from_margin(D("5620000"), D("0.12")) == D("6386363.6364")

    def test_margin_100_rejected(self):
        with pytest.raises(ValueError):
            selling_from_margin(D("100"), D("1"))

    def test_markup_vs_margin_distinct(self):
        # 25% markup on cost == 20% margin on price — they must not be conflated
        assert markup_to_margin(D("0.25")) == D("0.200000")


class TestCostEstimate:
    def test_total_with_contingency(self):
        sub, total = cost_estimate_total(material=D("1000"), fabrication=D("200"),
                                         labour=D("100"), freight=D("50"),
                                         overhead=D("150"), contingency_pct=D("0.10"))
        assert sub == D("1500.0000")
        assert total == D("1650.0000")

    def test_full_formula(self):
        sub, total = cost_estimate_total(material=D("1"), fabrication=D("2"), labour=D("3"),
                                         freight=D("4"), installation=D("5"),
                                         subcontracting=D("6"), overhead=D("7"))
        assert sub == D("28.0000") and total == D("28.0000")


class TestLandedCost:
    def test_recoverable_tax_excluded(self):
        # 55,500 + 800 freight, 18% recoverable tax → 56,300
        assert landed_unit_cost(D("55500"), D("1"), D("800"), D("0"), D("0.18"), True) == D("56300.0000")

    def test_non_recoverable_tax_included(self):
        # base 100, 10% non-recoverable tax → 110 + duty 0 + freight 0
        assert landed_unit_cost(D("100"), D("1"), D("0"), D("0"), D("0.10"), False) == D("110.0000")

    def test_fx_and_duty(self):
        # $100 * 83 + 5% duty + freight 1000 → 8300 + 415 + 1000 = 9715
        assert landed_unit_cost(D("100"), D("83"), D("1000"), D("0.05"), D("0"), True) == D("9715.0000")

    def test_seed_comparison_landings(self):
        assert landed_unit_cost(D("54900"), D("1"), D("1600")) == D("56500.0000")
        assert landed_unit_cost(D("56200"), D("1"), D("0")) == D("56200.0000")


class TestAverages:
    def test_wac(self):
        assert weighted_average_cost([(D("40"), D("54500")), (D("10"), D("56000"))]) == D("54800.0000")

    def test_wac_empty(self):
        assert weighted_average_cost([]) == D("0")

    def test_valuation(self):
        assert inventory_valuation([(D("40"), D("54500"))]) == D("2180000.0000")


class TestSupplierRanking:
    def test_ranking_by_landed(self):
        from app.calc.suppliers import Offer, rank_offers
        offers = [
            Offer("s1", "A", D("54900"), D("1"), D("1600"), D("0"), D("0.18"), True, 15, 30, True),
            Offer("s2", "B", D("56200"), D("1"), D("0"), D("0"), D("0.18"), True, 7, 30, True),
            Offer("s3", "C", D("55500"), D("1"), D("800"), D("0"), D("0.18"), True, 10, 30, True),
            Offer("s4", "D", D("50000"), D("1"), D("0"), D("0"), D("0"), True, 3, 30, False),
        ]
        ranked = rank_offers(offers)
        assert [r["supplier_name"] for r in ranked] == ["B", "C", "A"]
        assert ranked[0]["premium_vs_best"] == D("0.0000")
        assert ranked[1]["premium_vs_best"] == D("100.0000")
        assert ranked[2]["premium_vs_best"] == D("300.0000")

    def test_lead_time_demotion(self):
        from app.calc.suppliers import Offer, rank_offers
        offers = [
            Offer("s1", "CheapSlow", D("100"), D("1"), D("0"), D("0"), D("0"), True, 30, 30, True),
            Offer("s2", "ExpFast", D("105"), D("1"), D("0"), D("0"), D("0"), True, 5, 30, True),
        ]
        ranked = rank_offers(offers, max_lead_time_days=10)
        assert ranked[0]["supplier_name"] == "ExpFast"
        assert ranked[1]["lead_time_ok"] is False
