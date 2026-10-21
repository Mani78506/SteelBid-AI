from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID
import csv
import io

from fastapi import APIRouter, Depends, Header, Query, UploadFile, File
from sqlalchemy import desc, func, select

from app.calc.finance import q_money, q_ratio
from app.core.deps import TenantContext, require
from app.core.errors import bad_request, conflict, not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.market import MarketImportBatch, MarketImportStagedRow, MarketPriceAlertEvent, MarketPriceAlertRule, MarketSource, PriceObservation, PriceScenario, PriceSource
from app.models.ops import Notification
from app.schemas.market import (PriceObservationIn, PriceObservationOut, ScenarioIn,
                                ScenarioOut, TrendOut, TrendPoint, PriceAlertIn, PriceAlertUpdate)
from app.services.audit import record_audit
from app.services.market_ingestion import ingest_observations
from app.services.market_providers import ProviderObservation

router = APIRouter(prefix="/market", tags=["market"])


_PREVIEW_REQUIRED = ("material_form", "grade", "region", "price_per_unit", "currency", "unit", "price_basis", "observed_on")


def _preview_row(row: dict[str, str], row_number: int) -> tuple[dict, list[str], str | None]:
    raw = {str(k): (v or "").strip() for k, v in row.items() if k is not None}
    errors = [f"missing {field}" for field in _PREVIEW_REQUIRED if not raw.get(field)]
    normalized = dict(raw)
    if raw.get("price_per_unit"):
        try:
            price = Decimal(raw["price_per_unit"])
            if price <= 0:
                errors.append("price_per_unit must be positive")
            else:
                normalized["price_per_unit"] = str(price)
        except Exception:
            errors.append("price_per_unit must be a decimal")
    if raw.get("observed_on"):
        try:
            normalized["observed_on"] = date.fromisoformat(raw["observed_on"]).isoformat()
        except ValueError:
            errors.append("observed_on must be ISO-8601 (YYYY-MM-DD)")
    dedupe = None
    if not errors:
        dedupe = "|".join(normalized.get(f, "") for f in ("material_form", "grade", "dimension_note", "region", "price_per_unit", "currency", "unit", "price_basis", "observed_on"))
    return normalized, errors, dedupe


@router.post("/imports/preview", status_code=201)
def preview_import(
    source_id: UUID = Query(...),
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: TenantContext = Depends(require("market:write")),
):
    """Persist and validate CSV rows for review; this endpoint never publishes observations."""
    if not idempotency_key:
        raise bad_request("IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required")
    if not (file.filename or "").lower().endswith(".csv"):
        raise bad_request("INVALID_FILE", "Only CSV files are supported")
    source = ctx.db.get(MarketSource, source_id)
    visible = source and ((source.organization_id == ctx.org_id) or
                          (source.organization_id is None and source.visibility == "GLOBAL" and source.redistribution_permitted))
    if not visible:
        raise not_found("Market source")
    if source.license_status != "APPROVED":
        raise bad_request("SOURCE_NOT_AUTHORIZED", "Market source usage has not been approved")
    existing = ctx.db.scalar(select(MarketImportBatch).where(
        MarketImportBatch.organization_id == ctx.org_id,
        MarketImportBatch.import_key == idempotency_key))
    if existing:
        rows = ctx.db.scalars(select(MarketImportStagedRow).where(MarketImportStagedRow.batch_id == existing.id).order_by(MarketImportStagedRow.row_number)).all()
        return {"batch_id": str(existing.id), "status": existing.status, "idempotent_replay": True,
                "total_rows": existing.total_rows, "valid_rows": existing.valid_rows, "invalid_rows": existing.rejected_rows,
                "rows": [{"row_number": r.row_number, "status": r.status, "errors": r.validation_errors} for r in rows]}
    try:
        content = (file.file.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise bad_request("INVALID_ENCODING", "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise bad_request("INVALID_CSV", "CSV header row is required")
    batch = MarketImportBatch(organization_id=ctx.org_id, source_id=source.id, uploaded_by=ctx.user_id,
                              status="DRAFT", file_name=file.filename, import_key=idempotency_key)
    ctx.db.add(batch); ctx.db.flush()
    preview = []; valid = 0; invalid = 0
    for number, row in enumerate(reader, start=2):
        normalized, errors, dedupe = _preview_row(row, number)
        status = "VALID" if not errors else "INVALID"
        valid += status == "VALID"; invalid += status == "INVALID"
        staged = MarketImportStagedRow(batch_id=batch.id, row_number=number, original_data=row,
                                       normalized_data=normalized, validation_errors=errors,
                                       status=status, dedupe_key=dedupe)
        ctx.db.add(staged)
        preview.append({"row_number": number, "status": status, "errors": errors})
    batch.total_rows, batch.valid_rows, batch.rejected_rows = valid + invalid, valid, invalid
    batch.status = "VALIDATED" if valid else "DRAFT"
    record_audit(ctx, "market.preview_import", "market_import_batch", batch.id,
                 {"source_id": str(source.id), "total_rows": batch.total_rows, "valid_rows": valid, "invalid_rows": invalid})
    ctx.db.commit()
    return {"batch_id": str(batch.id), "status": batch.status, "idempotent_replay": False,
            "total_rows": batch.total_rows, "valid_rows": valid, "invalid_rows": invalid, "rows": preview}


def _obs_out(ctx: TenantContext, o: PriceObservation) -> PriceObservationOut:
    src = ctx.db.get(PriceSource, o.source_id) if o.source_id else None
    out = PriceObservationOut.model_validate(o)
    out.source_name = src.name if src else None
    return out


@router.get("/observations", response_model=Page[PriceObservationOut])
def list_observations(ctx: TenantContext = Depends(require("read")),
                      params: PageParams = Depends(), form: str | None = Query(None),
                      grade: str | None = Query(None), region: str | None = Query(None),
                      price_basis: str | None = Query(None)):
    stmt = select(PriceObservation).where(
        (PriceObservation.organization_id == ctx.org_id)
        | (PriceObservation.organization_id.is_(None)))
    if form:
        stmt = stmt.where(PriceObservation.material_form == form)
    if grade:
        stmt = stmt.where(PriceObservation.grade == grade)
    if region:
        stmt = stmt.where(PriceObservation.region == region)
    if price_basis:
        stmt = stmt.where(PriceObservation.price_basis == price_basis)
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


@router.post("/observations/import", status_code=201)
def import_observations(file: UploadFile = File(...),
                         ctx: TenantContext = Depends(require("market:write"))):
    """Bulk import price observations from CSV.
    CSV format: material_form,grade,region,dimension_note,price_basis,price_per_unit,unit,currency,observed_on
    All rows are attributed to the organization's MANUAL source and marked non-synthetic.
    """
    filename = file.filename or ""
    if not filename.lower().endswith('.csv'):
        from app.core.errors import bad_request
        raise bad_request("INVALID_FILE", "Only CSV files are supported")

    src = ctx.db.scalar(select(PriceSource).where(
        PriceSource.organization_id == ctx.org_id, PriceSource.source_type == "MANUAL"))
    if src is None:
        src = PriceSource(organization_id=ctx.org_id, name="Manual entry (team)",
                          source_type="MANUAL", is_synthetic=False)
        ctx.db.add(src)
        ctx.db.flush()

    content = file.file.read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because header is row 1
        try:
            form = row.get('material_form', '').strip()
            grade = row.get('grade', '').strip()
            region = row.get('region', '').strip()
            price_str = row.get('price_per_unit', '0').strip()

            # Validate required fields
            if not form or not grade or not region:
                errors.append(f"Row {row_num}: missing required fields (material_form, grade, region)")
                continue

            # Validate price is positive
            try:
                price = Decimal(price_str or '0')
                if price <= 0:
                    errors.append(f"Row {row_num}: price_per_unit must be positive, got {price}")
                    continue
            except:
                errors.append(f"Row {row_num}: invalid price_per_unit '{price_str}'")
                continue

            basis = row.get('price_basis', '').strip()
            if not basis:
                errors.append(f"Row {row_num}: missing price_basis; it cannot be inferred")
                continue
            observed_raw = row.get('observed_on', '').strip()
            if not observed_raw:
                errors.append(f"Row {row_num}: missing observed_on")
                continue
            obs = PriceObservation(
                organization_id=ctx.org_id,
                source_id=src.id,
                is_synthetic=False,
                material_form=form,
                grade=grade,
                region=region,
                dimension_note=row.get('dimension_note', '').strip() or None,
                price_basis=basis,
                price_per_unit=price,
                unit=row.get('unit', 'MT').strip() or 'MT',
                currency=row.get('currency', 'INR').strip() or 'INR',
                observed_on=date.fromisoformat(observed_raw)
            )
            ctx.db.add(obs)
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    ctx.db.flush()
    record_audit(ctx, "market.import_observations", "price_observation", None,
                 {"imported": imported, "errors": len(errors)})
    ctx.db.commit()

    return {"imported": imported, "errors": errors, "source_id": str(src.id)}


@router.get("/trends", response_model=TrendOut)
def trend(form: str, grade: str, region: str = "West India",
          price_basis: str | None = Query(None),
          days: int = Query(180, ge=7, le=730),
          ctx: TenantContext = Depends(require("read"))):
    since = date.today() - timedelta(days=days)
    stmt = select(PriceObservation).where(
        PriceObservation.material_form == form, PriceObservation.grade == grade,
        PriceObservation.region == region, PriceObservation.observed_on >= since,
        (PriceObservation.organization_id == ctx.org_id)
        | (PriceObservation.organization_id.is_(None)))
    if price_basis:
        stmt = stmt.where(PriceObservation.price_basis == price_basis)
    points = ctx.db.scalars(stmt.order_by(PriceObservation.observed_on)).all()
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


# ---- Comparable analytics -------------------------------------------------
# Analytics intentionally reads only organization-owned observations.  The
# legacy dashboard can surface permitted global demo data, but PriceSource has
# no entitlement relationship yet; including global rows here would silently
# broaden redistribution.  Provider work will add that explicit relationship.

def _owned_observations(ctx: TenantContext):
    return select(PriceObservation).where(PriceObservation.organization_id == ctx.org_id)


def _source_name(ctx: TenantContext, observation: PriceObservation) -> str:
    source = ctx.db.get(PriceSource, observation.source_id) if observation.source_id else None
    return source.name if source else "Unattributed observation"


def _observation_payload(ctx: TenantContext, observation: PriceObservation) -> dict:
    return {
        "id": str(observation.id), "material_form": observation.material_form,
        "grade": observation.grade, "region": observation.region,
        "price_basis": observation.price_basis, "currency": observation.currency,
        "unit": observation.unit, "price_per_unit": str(observation.price_per_unit),
        "observed_on": observation.observed_on.isoformat(),
        "source_id": str(observation.source_id) if observation.source_id else None,
        "source": _source_name(ctx, observation), "is_synthetic": observation.is_synthetic,
        "freshness_days": (date.today() - observation.observed_on).days,
    }


def _comparable_rows(
    ctx: TenantContext, *, form: str, grade: str, region: str,
    price_basis: str, currency: str, unit: str, source_id: UUID | None,
    since: date | None = None,
) -> tuple[list[PriceObservation], str | None]:
    stmt = _owned_observations(ctx).where(
        PriceObservation.material_form == form, PriceObservation.grade == grade,
        PriceObservation.region == region, PriceObservation.price_basis == price_basis,
        PriceObservation.currency == currency, PriceObservation.unit == unit)
    if source_id:
        stmt = stmt.where(PriceObservation.source_id == source_id)
    if since:
        stmt = stmt.where(PriceObservation.observed_on >= since)
    rows = ctx.db.scalars(stmt.order_by(PriceObservation.observed_on, PriceObservation.created_at)).all()
    sources = {row.source_id for row in rows}
    if source_id is None and len(sources) > 1:
        return [], "Multiple sources match this series; select a source before comparing prices."
    return rows, None


def _movement(rows: list[PriceObservation], days: int) -> dict:
    if not rows:
        return {"status": "insufficient_data", "reason": "No comparable observations."}
    latest = rows[-1]
    cutoff = latest.observed_on - timedelta(days=days)
    baseline = next((row for row in reversed(rows[:-1]) if row.observed_on <= cutoff), None)
    if baseline is None or baseline.price_per_unit == 0:
        return {"status": "insufficient_data", "reason": f"No comparable observation at least {days} days old."}
    absolute = latest.price_per_unit - baseline.price_per_unit
    return {"status": "ok", "from_observation_date": baseline.observed_on.isoformat(),
            "absolute_change": str(absolute),
            "percentage_change": str(q_ratio(absolute / baseline.price_per_unit))}


@router.get("/intelligence/history")
def intelligence_history(
    material_form: str, grade: str, region: str, price_basis: str,
    currency: str = "INR", unit: str = "MT", source_id: UUID | None = None,
    days: int = Query(30, ge=7, le=365),
    ctx: TenantContext = Depends(require("read")),
):
    """Comparable historical observations; never interpolates missing dates."""
    rows, reason = _comparable_rows(ctx, form=material_form, grade=grade, region=region,
                                    price_basis=price_basis, currency=currency, unit=unit,
                                    source_id=source_id, since=date.today() - timedelta(days=days))
    if reason:
        return {"status": "insufficient_data", "reason": reason, "points": []}
    return {"status": "ok" if rows else "insufficient_data",
            "reason": None if rows else "No observations in the requested period.",
            "comparison_key": {"material_form": material_form, "grade": grade, "region": region,
                               "price_basis": price_basis, "currency": currency, "unit": unit,
                               "source_id": str(rows[0].source_id) if rows else None},
            "points": [_observation_payload(ctx, row) for row in rows]}


@router.get("/intelligence/latest")
def intelligence_latest(
    material_form: str, grade: str, region: str, price_basis: str,
    currency: str = "INR", unit: str = "MT", source_id: UUID | None = None,
    ctx: TenantContext = Depends(require("read")),
):
    rows, reason = _comparable_rows(ctx, form=material_form, grade=grade, region=region,
                                    price_basis=price_basis, currency=currency, unit=unit,
                                    source_id=source_id)
    if reason or not rows:
        return {"status": "insufficient_data", "reason": reason or "No comparable observations.", "latest": None}
    latest = rows[-1]
    return {"status": "ok", "latest": _observation_payload(ctx, latest),
            "previous": _observation_payload(ctx, rows[-2]) if len(rows) > 1 else None,
            "movement": {str(window): _movement(rows, window) for window in (7, 30, 90, 365)},
            "minimum": str(min(row.price_per_unit for row in rows)),
            "maximum": str(max(row.price_per_unit for row in rows)),
            "average": str(sum((row.price_per_unit for row in rows), Decimal("0")) / Decimal(len(rows)))}


@router.get("/intelligence/overview")
def intelligence_overview(limit: int = Query(24, ge=1, le=100), ctx: TenantContext = Depends(require("read"))):
    """One latest record per fully compatible series; no cross-series averages."""
    rows = ctx.db.scalars(_owned_observations(ctx).order_by(PriceObservation.observed_on.desc(), PriceObservation.created_at.desc())).all()
    latest_by_series: dict[tuple, PriceObservation] = {}
    for row in rows:
        identity = (row.material_form, row.grade, row.region, row.price_basis, row.currency, row.unit, row.source_id)
        latest_by_series.setdefault(identity, row)
    cards = []
    for row in list(latest_by_series.values())[:limit]:
        series = [candidate for candidate in rows if (candidate.material_form, candidate.grade, candidate.region,
                  candidate.price_basis, candidate.currency, candidate.unit, candidate.source_id) ==
                  (row.material_form, row.grade, row.region, row.price_basis, row.currency, row.unit, row.source_id)]
        cards.append({**_observation_payload(ctx, row), "movement_7d": _movement(series, 7),
                      "movement_30d": _movement(series, 30), "movement_90d": _movement(series, 90)})
    return {"status": "ok" if cards else "insufficient_data", "cards": cards}


@router.get("/intelligence/regions")
def intelligence_regions(
    material_form: str, grade: str, price_basis: str, currency: str = "INR", unit: str = "MT",
    source_id: UUID | None = None, ctx: TenantContext = Depends(require("read")),
):
    """Latest prices by region, constrained to one source and comparable units/basis."""
    stmt = _owned_observations(ctx).where(PriceObservation.material_form == material_form,
        PriceObservation.grade == grade, PriceObservation.price_basis == price_basis,
        PriceObservation.currency == currency, PriceObservation.unit == unit)
    if source_id:
        stmt = stmt.where(PriceObservation.source_id == source_id)
    rows = ctx.db.scalars(stmt.order_by(PriceObservation.observed_on, PriceObservation.created_at)).all()
    source_ids = {row.source_id for row in rows}
    if not rows or (source_id is None and len(source_ids) > 1):
        return {"status": "insufficient_data", "reason": "Select one source for a regional comparison." if rows else "No comparable observations.", "regions": []}
    latest_by_region: dict[str, PriceObservation] = {}
    for row in rows:
        latest_by_region[row.region] = row
    return {"status": "ok", "regions": [_observation_payload(ctx, row) for row in latest_by_region.values()]}


@router.get("/intelligence/movers")
def intelligence_movers(
    days: int = Query(30, ge=7, le=365), limit: int = Query(10, ge=1, le=50),
    ctx: TenantContext = Depends(require("read")),
):
    """Largest movements per strictly comparable tenant-owned series."""
    rows = ctx.db.scalars(_owned_observations(ctx).order_by(PriceObservation.observed_on, PriceObservation.created_at)).all()
    groups: dict[tuple, list[PriceObservation]] = {}
    for row in rows:
        groups.setdefault((row.material_form, row.grade, row.region, row.price_basis, row.currency, row.unit, row.source_id), []).append(row)
    movers = []
    for _, group in groups.items():
        result = _movement(group, days)
        if result["status"] == "ok":
            latest = _observation_payload(ctx, group[-1])
            movers.append({**latest, "movement": result})
    movers.sort(key=lambda item: Decimal(item["movement"]["percentage_change"]), reverse=True)
    return {"window_days": days, "increases": movers[:limit], "decreases": list(reversed(movers[-limit:]))}


@router.get("/intelligence/sources")
def intelligence_sources(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.scalars(_owned_observations(ctx).order_by(PriceObservation.observed_on.desc())).all()
    latest_by_source: dict[UUID | None, PriceObservation] = {}
    for row in rows:
        latest_by_source.setdefault(row.source_id, row)
    return {"sources": [{"source_id": str(source_id) if source_id else None,
                         "name": _source_name(ctx, observation), "latest_observed_on": observation.observed_on.isoformat(),
                         "freshness_days": (date.today() - observation.observed_on).days,
                         "synthetic": observation.is_synthetic}
                        for source_id, observation in latest_by_source.items()]}


@router.get("/intelligence/freshness")
def intelligence_freshness(stale_after_days: int = Query(14, ge=1, le=365), ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.scalars(_owned_observations(ctx).order_by(PriceObservation.observed_on.desc())).all()
    latest_by_series: dict[tuple, PriceObservation] = {}
    for row in rows:
        latest_by_series.setdefault((row.material_form, row.grade, row.region, row.price_basis, row.currency, row.unit, row.source_id), row)
    series = [{**_observation_payload(ctx, row), "stale": (date.today() - row.observed_on).days > stale_after_days}
              for row in latest_by_series.values()]
    return {"stale_after_days": stale_after_days, "series": series}


def _alert_out(rule: MarketPriceAlertRule) -> dict:
    return {"id": str(rule.id), "material_form": rule.material_form, "grade": rule.grade, "region": rule.region,
            "currency": rule.currency, "unit": rule.unit, "price_basis": rule.price_basis,
            "source_id": str(rule.source_id) if rule.source_id else None, "price_condition": rule.price_condition,
            "price_threshold": str(rule.price_threshold) if rule.price_threshold is not None else None,
            "movement_threshold_pct": str(rule.movement_threshold_pct) if rule.movement_threshold_pct is not None else None,
            "is_active": rule.is_active, "created_at": rule.created_at.isoformat()}


@router.post("/alerts", status_code=201)
def create_alert(body: PriceAlertIn, ctx: TenantContext = Depends(require("market:write"))):
    if body.price_threshold is None and body.movement_threshold_pct is None:
        raise bad_request("ALERT_CONDITION_REQUIRED", "A price or movement threshold is required")
    if body.source_id:
        source = ctx.db.get(PriceSource, body.source_id)
        if source is None or source.organization_id != ctx.org_id:
            raise not_found("Price source")
    rule = MarketPriceAlertRule(organization_id=ctx.org_id, user_id=ctx.user_id, **body.model_dump())
    ctx.db.add(rule); ctx.db.commit(); ctx.db.refresh(rule)
    return _alert_out(rule)


@router.get("/alerts")
def list_alerts(ctx: TenantContext = Depends(require("read"))):
    rules = ctx.db.scalars(select(MarketPriceAlertRule).where(MarketPriceAlertRule.organization_id == ctx.org_id,
        MarketPriceAlertRule.user_id == ctx.user_id).order_by(MarketPriceAlertRule.created_at.desc())).all()
    return {"items": [_alert_out(rule) for rule in rules]}


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: UUID, body: PriceAlertUpdate, ctx: TenantContext = Depends(require("market:write"))):
    rule = ctx.db.scalar(select(MarketPriceAlertRule).where(MarketPriceAlertRule.id == alert_id,
        MarketPriceAlertRule.organization_id == ctx.org_id, MarketPriceAlertRule.user_id == ctx.user_id))
    if rule is None: raise not_found("Price alert")
    for field, value in body.model_dump(exclude_unset=True).items(): setattr(rule, field, value)
    if rule.price_threshold is None and rule.movement_threshold_pct is None:
        raise bad_request("ALERT_CONDITION_REQUIRED", "A price or movement threshold is required")
    ctx.db.commit(); return _alert_out(rule)


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: UUID, ctx: TenantContext = Depends(require("market:write"))):
    rule = ctx.db.scalar(select(MarketPriceAlertRule).where(MarketPriceAlertRule.id == alert_id,
        MarketPriceAlertRule.organization_id == ctx.org_id, MarketPriceAlertRule.user_id == ctx.user_id))
    if rule is None: raise not_found("Price alert")
    ctx.db.delete(rule); ctx.db.commit()


@router.get("/alerts/history")
def alert_history(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.execute(select(MarketPriceAlertEvent, MarketPriceAlertRule, Notification, PriceObservation)
        .join(MarketPriceAlertRule, MarketPriceAlertEvent.alert_rule_id == MarketPriceAlertRule.id)
        .join(Notification, MarketPriceAlertEvent.notification_id == Notification.id)
        .join(PriceObservation, MarketPriceAlertEvent.observation_id == PriceObservation.id)
        .where(MarketPriceAlertEvent.organization_id == ctx.org_id, MarketPriceAlertRule.user_id == ctx.user_id)
        .order_by(MarketPriceAlertEvent.created_at.desc())).all()
    return {"items": [{"event_id": str(event.id), "alert_id": str(rule.id), "trigger_type": event.trigger_type,
                       "notification_id": str(notification.id), "notification_title": notification.title,
                       "observation": _observation_payload(ctx, observation), "created_at": event.created_at.isoformat()}
                      for event, rule, notification, observation in rows]}


@router.post("/demo/trigger-alert")
def trigger_showcase_alert(ctx: TenantContext = Depends(require("market:write"))):
    """Controlled, repeatable demo-only ingestion. Never available to customer organizations."""
    if not ctx.organization.is_demo or ctx.organization.name != "[DEMO] SteelBid Market Showcase":
        raise not_found("Demo alert action")
    source = ctx.db.scalar(select(PriceSource).where(PriceSource.organization_id == ctx.org_id,
        PriceSource.source_type == "SYNTHETIC"))
    if source is None: raise bad_request("DEMO_SOURCE_MISSING", "Showcase synthetic source is unavailable")
    rule = ctx.db.scalar(select(MarketPriceAlertRule).where(MarketPriceAlertRule.organization_id == ctx.org_id,
        MarketPriceAlertRule.user_id == ctx.user_id, MarketPriceAlertRule.material_form == "HRC",
        MarketPriceAlertRule.grade == "E250", MarketPriceAlertRule.region == "West India",
        MarketPriceAlertRule.source_id == source.id).limit(1))
    if rule is None:
        rule = MarketPriceAlertRule(organization_id=ctx.org_id, user_id=ctx.user_id, source_id=source.id,
            material_form="HRC", grade="E250", region="West India", currency="INR", unit="MT",
            price_basis="EX_WORKS", price_condition="ABOVE", price_threshold=Decimal("56500"), is_active=True)
        ctx.db.add(rule)
    else:
        rule.price_condition, rule.price_threshold, rule.is_active = "ABOVE", Decimal("56500"), True
    ctx.db.commit()
    replay_key = f"showcase-alert-replay-{ctx.user_id}"
    replay_price = Decimal("57000") + Decimal(int(ctx.user_id.hex[:4], 16) % 100)
    run = ingest_observations(ctx.db, organization_id=ctx.org_id, source_id=source.id,
        provider_key="DEMO_PROVIDER", idempotency_key=replay_key, is_synthetic=True,
        observations=[ProviderObservation(material_form="HRC", grade="E250", region="West India",
            price_per_unit=replay_price, currency="INR", unit="MT", price_basis="EX_WORKS",
            observed_on=date.today(), external_observation_id=replay_key)])
    return {"run_id": str(run.id), "status": run.status, "inserted": run.inserted_count,
            "duplicates": run.duplicate_count, "rejected": run.rejected_count,
            "message": "Synthetic Showcase observation replayed through the ingestion pipeline."}


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
