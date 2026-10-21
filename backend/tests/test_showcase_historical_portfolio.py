from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models.identity import Organization
from app.models.market import PriceObservation
from app.models.ops import CostEstimate, Notification
from app.models.projects import Tender


def test_showcase_has_isolated_non_monotonic_market_history_and_portfolio(db):
    org = db.scalar(select(Organization).where(Organization.name == "[DEMO] SteelBid Market Showcase"))
    rows = db.scalars(select(PriceObservation).where(PriceObservation.organization_id == org.id,
        PriceObservation.material_form == "HRC", PriceObservation.grade == "E250", PriceObservation.region == "West India").order_by(PriceObservation.observed_on)).all()
    assert len(rows) == 366
    assert all(row.is_synthetic for row in rows)
    changes = [rows[i].price_per_unit - rows[i - 1].price_per_unit for i in range(1, len(rows))]
    assert any(change > 0 for change in changes) and any(change < 0 for change in changes)
    assert db.scalar(select(func.count()).select_from(Tender).where(Tender.organization_id == org.id)) == 7
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.organization_id == org.id)) >= 4


def test_historical_tender_benchmark_never_uses_future_observation(db):
    org = db.scalar(select(Organization).where(Organization.name == "[DEMO] SteelBid Market Showcase"))
    estimates = db.scalars(select(CostEstimate).where(CostEstimate.organization_id == org.id, CostEstimate.tender_id.is_not(None))).all()
    linked = [estimate for estimate in estimates if estimate.context.get("historical_market_benchmark")]
    assert len(linked) >= 6
    for estimate in linked:
        benchmark = estimate.context["historical_market_benchmark"]
        assert date.fromisoformat(benchmark["observed_on"]) <= date.fromisoformat(estimate.context["costing_reference_date"])
        assert Decimal(benchmark["unit_price"]) > 0
        assert benchmark["price_basis"] == "EX_WORKS"
