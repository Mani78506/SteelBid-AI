from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.ai.briefing import answer_copilot, explain_shortage, generate_daily_briefing
from app.ai.providers import get_provider
from app.calc.suppliers import Offer, rank_offers
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.models.market import PriceObservation
from app.models.ops import AIJob
from app.models.procurement import Supplier, SupplierQuote
from app.schemas.ops import AIJobOut, CopilotIn, ExplainIn

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/explain")
def explain(body: ExplainIn, ctx: TenantContext = Depends(require("ai:use"))):
    """Grounded explanations over real records. Recorded as an AI job for traceability."""
    job = AIJob(organization_id=ctx.org_id, job_type="EXPLANATION", status="RUNNING",
                input=body.model_dump(mode="json"), created_by=ctx.user_id)
    ctx.db.add(job)
    ctx.db.flush()
    try:
        if body.topic == "shortage":
            material_id = UUID(body.entity["material_id"])
            required = Decimal(str(body.entity["required_qty"]))
            result = explain_shortage(ctx.db, ctx.org_id, material_id, required)
        elif body.topic == "supplier_comparison":
            material_id = UUID(body.entity["material_id"])
            quotes = ctx.db.scalars(select(SupplierQuote).where(
                SupplierQuote.organization_id == ctx.org_id,
                SupplierQuote.material_id == material_id,
                SupplierQuote.status == "OPEN")).all()
            from datetime import date
            offers = []
            for q in quotes:
                if q.valid_until and q.valid_until < date.today():
                    continue
                s = ctx.db.get(Supplier, q.supplier_id)
                offers.append(Offer(
                    supplier_id=str(q.supplier_id), supplier_name=s.name if s else "?",
                    unit_price=q.unit_price, fx_rate=q.fx_rate_to_org_ccy,
                    freight_per_unit=q.freight_per_unit, duty_pct=q.duty_pct,
                    tax_pct=q.tax_pct, tax_recoverable=q.tax_recoverable,
                    lead_time_days=q.lead_time_days, payment_terms_days=q.payment_terms_days,
                    valid=True))
            ranked = rank_offers(offers)
            if not ranked:
                raise bad_request("NO_OFFERS", "No valid supplier offers for this material")
            best = ranked[0]
            explanation = (f"{best['supplier_name']} offers the lowest landed cost at "
                           f"{best['landed_cost']} per unit (lead time {best['lead_time_days']} days, "
                           f"payment {best['payment_terms_days']} days). "
                           + "; ".join(f"{r['supplier_name']} lands at {r['landed_cost']} "
                                       f"(+{r['premium_vs_best']} vs best)"
                                       for r in ranked[1:]))
            result = {"explanation": explanation,
                      "ranking": [{**r, "landed_cost": str(r["landed_cost"]),
                                   "premium_vs_best": str(r["premium_vs_best"]),
                                   "unit_price": str(r["unit_price"])} for r in ranked],
                      "grounded_in": [{"entity": "supplier_quote", "supplier_id": r["supplier_id"]}
                                      for r in ranked]}
        else:  # price_risk COUNT
            form = body.entity["form"]
            grade = body.entity["grade"]
            region = body.entity.get("region", "West India")
            qty = Decimal(str(body.entity.get("planned_qty", "100")))
            latest = ctx.db.scalars(select(PriceObservation).where(
                PriceObservation.material_form == form, PriceObservation.grade == grade,
                PriceObservation.region == region,
                (PriceObservation.organization_id == ctx.org_id)
                | (PriceObservation.organization_id.is_(None)))
                .order_by(PriceObservation.observed_on.desc())).first()
            if latest is None:
                raise bad_request("NO_PRICE_DATA", "No observations for this material/region")
            up5 = latest.price_per_unit * Decimal("1.05")
            down5 = latest.price_per_unit * Decimal("0.95")
            result = {"explanation": (
                f"Latest observation for {form} {grade} in {region}: {latest.price_per_unit} "
                f"{latest.currency}/{latest.unit} (observed {latest.observed_on}"
                f"{', labeled synthetic demo data' if latest.is_synthetic else ''}). "
                f"A ±5% swing on {qty} {latest.unit} changes exposure by "
                f"±{(latest.price_per_unit * Decimal('0.05') * qty).quantize(Decimal('0.01'))} "
                f"{latest.currency} "
                f"(to {up5.quantize(Decimal('0.01'))}–{down5.quantize(Decimal('0.01'))}). "
                "This is scenario arithmetic, not a forecast."),
                "grounded_in": [{"entity": "price_observation", "id": str(latest.id)}],
                "data_is_synthetic": latest.is_synthetic}
        job.status = "SUCCEEDED"
        job.output = result
    except Exception as exc:
        job.status = "FAILED"
        job.error = str(exc)[:2000]
        ctx.db.commit()
        raise
    from datetime import datetime, timezone
    job.completed_at = datetime.now(timezone.utc)
    ctx.db.commit()
    return {**result, "provider": get_provider().name,
            "note": "AI explains records; it does not decide. Approvals remain human."}


@router.post("/copilot")
def copilot(body: CopilotIn, ctx: TenantContext = Depends(require("ai:use"))):
    job = AIJob(organization_id=ctx.org_id, job_type="BRIEFING" if not body.project_id else "EXPLANATION",
                status="RUNNING", input=body.model_dump(mode="json"), created_by=ctx.user_id)
    ctx.db.add(job)
    ctx.db.flush()
    result = answer_copilot(ctx.db, ctx.org_id, body.question, body.project_id)
    from datetime import datetime, timezone
    job.status = "SUCCEEDED"
    job.output = result
    job.completed_at = datetime.now(timezone.utc)
    ctx.db.commit()
    return {**result, "provider": get_provider().name}


@router.get("/daily-briefing")
def daily_briefing(ctx: TenantContext = Depends(require("read"))):
    return generate_daily_briefing(ctx.db, ctx.org_id, ctx.organization.currency_code)


@router.get("/jobs", response_model=list[AIJobOut])
def list_jobs(ctx: TenantContext = Depends(require("read")),
              job_type: str | None = Query(None)):
    stmt = select(AIJob).where(AIJob.organization_id == ctx.org_id)
    if job_type:
        stmt = stmt.where(AIJob.job_type == job_type)
    rows = ctx.db.scalars(stmt.order_by(AIJob.created_at.desc()).limit(50)).all()
    return [AIJobOut.model_validate(r) for r in rows]
