from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select

from app.calc.finance import q_money, q_ratio
from app.core.deps import TenantContext, require
from app.core.pagination import Page, PageParams, paginate
from app.models.market import PriceObservation, PriceScenario, PriceSource
from app.schemas.market import (PriceObservationIn, PriceObservationOut, ScenarioIn,
                                ScenarioOut, TrendOut, TrendPoint)
from app.services.audit import record_audit

router = APIRouter(prefix="/market", tags=["market"])


def _obs_out(ctx: TenantContext, o: PriceObservation) -> PriceObservationOut:
    src = ctx.db.get(PriceSource, o.source_id) if o.source_id else None
    out = PriceObservationOut.model_validate(o)
    out.source_name = src.name if src else None
    return out


@router.get("/observations", response_model=Page[PriceObservationOut])
def list_observations(ctx: TenantContext = Depends(require("read")),
                      params: PageParams = Depends(), form: str | None = Query(None),
                      grade: str | None = Query(None), region: str | None = Query(None)):
    stmt = select(PriceObservation).where(
        (PriceObservation.organization_id == ctx.org_id)
        | (PriceObservation.organization_id.is_(None)))
    if form:
        stmt = stmt.where(PriceObservation.material_form == form)
    if grade:
        stmt = stmt.where(PriceObservation.grade == grade)
    if region:
        stmt = stmt.where(PriceObservation.region == region)
    stmt = stmt.order_by(desc(PriceObservation.observed_on))
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_obs_out(ctx, o) for o in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/observations", response_model=PriceObservationOut, status_code=201)
def add_observation(body: PriceObservationIn,
                    ctx: TenantContext = Depends(require("market:write"))):
    """Manual price observation entry — always attributed, never synthetic."""
    src = ctx.db.scalar(select(PriceSource).where(
        PriceSource.organization_id == ctx.org_id, PriceSource.source_type == "MANUAL"))
    if src is None:
        src = PriceSource(organization_id=ctx.org_id, name="Manual entry (team)",
                          source_type="MANUAL", is_synthetic=False)
        ctx.db.add(src)
        ctx.db.flush()
    o = PriceObservation(organization_id=ctx.org_id, source_id=src.id,
                         is_synthetic=False, **body.model_dump())
    ctx.db.add(o)
    ctx.db.flush()
    record_audit(ctx, "market.add_observation", "price_observation", o.id,
                 {"after": body.model_dump()})
    ctx.db.commit()
    return _obs_out(ctx, o)


@router.get("/trends", response_model=TrendOut)
def trend(form: str, grade: str, region: str = "West India",
          days: int = Query(180, ge=7, le=730),
          ctx: TenantContext = Depends(require("read"))):
    since = date.today() - timedelta(days=days)
    points = ctx.db.scalars(select(PriceObservation).where(
        PriceObservation.material_form == form, PriceObservation.grade == grade,
        PriceObservation.region == region, PriceObservation.observed_on >= since,
        (PriceObservation.organization_id == ctx.org_id)
        | (PriceObservation.organization_id.is_(None)))
        .order_by(PriceObservation.observed_on)).all()
    latest = points[-1] if points else None
    is_synth = all(p.is_synthetic for p in points) if points else True

    def pct_change(window: int) -> Decimal | None:
        cutoff = date.today() - timedelta(days=window)
        older = [p for p in points if p.observed_on <= cutoff]
        if not older or not latest or older[-1].price_per_unit == 0:
            return None
        return q_ratio((latest.price_per_unit - older[-1].price_per_unit)
                       / older[-1].price_per_unit)

    return TrendOut(
        material_form=form, grade=grade, region=region,
        points=[TrendPoint(observed_on=p.observed_on, price_per_unit=p.price_per_unit,
                           is_synthetic=p.is_synthetic) for p in points],
        latest=latest.price_per_unit if latest else None,
        change_pct_30d=pct_change(30), change_pct_90d=pct_change(90),
        data_is_synthetic=is_synth,
        freshness_days=(date.today() - latest.observed_on).days if latest else None)


@router.get("/freshness-warnings")
def freshness(ctx: TenantContext = Depends(require("read"))):
    """Data freshness warnings: form/grade/region combos whose latest observation is stale."""
    rows = ctx.db.execute(
        select(PriceObservation.material_form, PriceObservation.grade, PriceObservation.region,
               func.max(PriceObservation.observed_on)).where(
            (PriceObservation.organization_id == ctx.org_id)
            | (PriceObservation.organization_id.is_(None)))
        .group_by(PriceObservation.material_form, PriceObservation.grade,
                  PriceObservation.region)).all()
    warnings = []
    for form_, grade_, region_, latest_on in rows:
        age = (date.today() - latest_on).days
        if age > 14:
            warnings.append({"material_form": form_, "grade": grade_, "region": region_,
                             "latest_observation": str(latest_on), "age_days": age,
                             "warning": "Price data is stale; treat as indicative only."})
    return {"warnings": warnings}


@router.post("/scenarios", response_model=ScenarioOut, status_code=201)
def run_scenario(body: ScenarioIn, ctx: TenantContext = Depends(require("market:write"))):
    """Price scenario analysis: price_delta_pct applied to latest observed price over horizon.
    Deterministic arithmetic only — no fabricated forecasts."""
    latest = ctx.db.scalars(select(PriceObservation).where(
        PriceObservation.material_form == body.material_form,
        PriceObservation.grade == body.grade, PriceObservation.region == body.region,
        (PriceObservation.organization_id == ctx.org_id)
        | (PriceObservation.organization_id.is_(None)))
        .order_by(desc(PriceObservation.observed_on))).first()
    if latest is None:
        from app.core.errors import bad_request
        raise bad_request("NO_PRICE_DATA", "No price observations for this material/region")
    base = latest.price_per_unit
    scenario_price = q_money(base * (Decimal("1") + body.price_delta_pct))
    exposure = q_money(scenario_price * body.planned_qty)
    baseline_exposure = q_money(base * body.planned_qty)
    results = {
        "base_price": str(base), "scenario_price": str(scenario_price),
        "planned_qty": str(body.planned_qty), "unit": body.unit,
        "baseline_exposure": str(baseline_exposure), "scenario_exposure": str(exposure),
        "exposure_delta": str(q_money(exposure - baseline_exposure)),
        "based_on_observation": str(latest.observed_on),
        "data_is_synthetic": latest.is_synthetic,
        "disclaimer": ("Indicative analysis from labeled observations; not a price forecast. "
                       + ("Underlying data is synthetic demo data." if latest.is_synthetic else "")),
    }
    s = PriceScenario(organization_id=ctx.org_id, name=body.name,
                      parameters=body.model_dump(mode="json"), results=results,
                      created_by=ctx.user_id)
    ctx.db.add(s)
    ctx.db.flush()
    record_audit(ctx, "market.run_scenario", "price_scenario", s.id, {"after": results})
    ctx.db.commit()
    return ScenarioOut.model_validate(s)


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_scenarios(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.scalars(select(PriceScenario).where(
        PriceScenario.organization_id == ctx.org_id)
        .order_by(PriceScenario.created_at.desc()).limit(50)).all()
    return [ScenarioOut.model_validate(r) for r in rows]
