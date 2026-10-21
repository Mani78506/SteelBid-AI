"""Price alert evaluation invoked only for newly persisted observations."""
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market import MarketPriceAlertEvent, MarketPriceAlertRule, PriceObservation, PriceSource
from app.models.ops import Notification

STALE_AFTER_DAYS = 14

def _matches(rule: MarketPriceAlertRule, obs: PriceObservation) -> bool:
    return (rule.material_form == obs.material_form and rule.grade == obs.grade and rule.region == obs.region
            and rule.currency == obs.currency and rule.unit == obs.unit and rule.price_basis == obs.price_basis
            and (rule.source_id is None or rule.source_id == obs.source_id))

def _price_met(rule: MarketPriceAlertRule, price: Decimal) -> bool:
    if rule.price_threshold is None: return False
    return price >= rule.price_threshold if rule.price_condition == "ABOVE" else price <= rule.price_threshold

def evaluate_price_alerts(db: Session, observation: PriceObservation) -> int:
    """Emit one event only on a price-threshold crossing; stale data never alerts."""
    if observation.observed_on < date.today() - timedelta(days=STALE_AFTER_DAYS):
        return 0
    rules = db.scalars(select(MarketPriceAlertRule).where(MarketPriceAlertRule.organization_id == observation.organization_id,
        MarketPriceAlertRule.is_active.is_(True))).all()
    previous = db.scalar(select(PriceObservation).where(PriceObservation.organization_id == observation.organization_id,
        PriceObservation.material_form == observation.material_form, PriceObservation.grade == observation.grade,
        PriceObservation.region == observation.region, PriceObservation.currency == observation.currency,
        PriceObservation.unit == observation.unit, PriceObservation.price_basis == observation.price_basis,
        PriceObservation.source_id == observation.source_id, PriceObservation.observed_on < observation.observed_on)
        .order_by(PriceObservation.observed_on.desc(), PriceObservation.created_at.desc()).limit(1))
    source = db.get(PriceSource, observation.source_id)
    emitted = 0
    for rule in rules:
        if not _matches(rule, observation): continue
        price_crossed = _price_met(rule, observation.price_per_unit) and (previous is None or not _price_met(rule, previous.price_per_unit))
        movement_crossed = False
        if rule.movement_threshold_pct is not None and previous and previous.price_per_unit:
            change = (observation.price_per_unit - previous.price_per_unit) / previous.price_per_unit
            movement_crossed = change >= rule.movement_threshold_pct if rule.price_condition == "ABOVE" else change <= -rule.movement_threshold_pct
        if not (price_crossed or movement_crossed): continue
        existing = db.scalar(select(MarketPriceAlertEvent.id).where(MarketPriceAlertEvent.alert_rule_id == rule.id,
            MarketPriceAlertEvent.observation_id == observation.id))
        if existing: continue
        condition = "above" if rule.price_condition == "ABOVE" else "below"
        threshold = str(rule.price_threshold) if rule.price_threshold is not None else f"{rule.movement_threshold_pct * Decimal('100')}% movement"
        notification = Notification(organization_id=observation.organization_id, user_id=rule.user_id, kind="MARKET_ALERT",
            title=f"Price alert: {observation.material_form} {observation.grade}",
            body=(f"{observation.region}: {observation.currency} {observation.price_per_unit}/{observation.unit} is {condition} "
                  f"{threshold}; observed {observation.observed_on.isoformat()} from {source.name if source else 'attributed source'}"),
            link=f"/market?observation_id={observation.id}")
        db.add(notification); db.flush()
        db.add(MarketPriceAlertEvent(organization_id=observation.organization_id, alert_rule_id=rule.id,
            observation_id=observation.id, notification_id=notification.id,
            trigger_type="PRICE" if price_crossed else "MOVEMENT"))
        emitted += 1
    return emitted
