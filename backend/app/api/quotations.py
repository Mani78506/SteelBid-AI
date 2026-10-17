from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select

from app.core.deps import TenantContext, require
from app.core.errors import conflict, forbidden, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.crm import Customer
from app.models.sales import Quotation, QuotationItem, QuotationVersion
from app.schemas.sales import (ApproveIn, QuotationCreateIn, QuotationOut, QuotationUpdateIn,
                               QuotationVersionOut)
from app.services.audit import record_audit
from app.services.quotations import (approve_quotation, build_quotation_pdf_html,
                                     convert_to_sales_order, create_quotation,
                                     get_quotation_scoped, submit_for_approval,
                                     transition_quotation, _build_version, _current_version)

router = APIRouter(prefix="/quotations", tags=["quotations"])


def _out(ctx: TenantContext, q: Quotation, with_items: bool = True) -> QuotationOut:
    from app.schemas.sales import QuotationItemOut
    customer = ctx.db.get(Customer, q.customer_id)
    versions = ctx.db.scalars(select(QuotationVersion).where(
        QuotationVersion.quotation_id == q.id).order_by(QuotationVersion.version_no)).all()
    out = QuotationOut.model_validate(q)
    out.customer_name = customer.name if customer else None
    out.versions = [QuotationVersionOut.model_validate(v) for v in versions]
    if with_items and versions:
        items = ctx.db.scalars(select(QuotationItem).where(
            QuotationItem.quotation_version_id == versions[-1].id)).all()
        out.items = [QuotationItemOut.model_validate(i) for i in items]
    return out


@router.get("", response_model=Page[QuotationOut])
def list_quotations(ctx: TenantContext = Depends(require("read")),
                    params: PageParams = Depends(), search: str | None = Query(None),
                    status: str | None = Query(None), customer_id: UUID | None = Query(None)):
    stmt = select(Quotation).where(Quotation.organization_id == ctx.org_id)
    if search:
        stmt = stmt.where(or_(Quotation.number.ilike(f"%{search}%")))
    if status:
        stmt = stmt.where(Quotation.status == status)
    if customer_id:
        stmt = stmt.where(Quotation.customer_id == customer_id)
    stmt = apply_sort(stmt, params.sort, {"created_at": Quotation.created_at,
                                          "number": Quotation.number, "status": Quotation.status},
                      Quotation.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_out(ctx, q) for q in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("", response_model=QuotationOut, status_code=201)
def create(body: QuotationCreateIn, ctx: TenantContext = Depends(require("quotations:write"))):
    q = create_quotation(ctx, body)
    record_audit(ctx, "quotation.create", "quotation", q.id,
                 {"after": {"number": q.number, "customer_id": str(body.customer_id)}})
    ctx.db.commit()
    return _out(ctx, q)


@router.get("/{quotation_id}", response_model=QuotationOut)
def get_one(quotation_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _out(ctx, get_quotation_scoped(ctx, quotation_id))


@router.patch("/{quotation_id}", response_model=QuotationOut)
def revise(quotation_id: UUID, body: QuotationUpdateIn,
           ctx: TenantContext = Depends(require("quotations:write"))):
    q = get_quotation_scoped(ctx, quotation_id)
    if q.status not in ("DRAFT", "PENDING_APPROVAL", "REJECTED"):
        raise conflict("IMMUTABLE", f"Quotation in status {q.status} cannot be revised")
    version_no = ctx.db.scalar(
        select(QuotationVersion.version_no).where(QuotationVersion.quotation_id == q.id)
        .order_by(QuotationVersion.version_no.desc()).limit(1)) or 0
    q.target_margin = body.target_margin
    q.valid_until = body.valid_until
    q.status = "DRAFT"
    _build_version(ctx, q, version_no=version_no + 1, items_in=body.items,
                   target_margin=body.target_margin)
    record_audit(ctx, "quotation.revise", "quotation", q.id,
                 {"after": {"version_no": version_no + 1}})
    ctx.db.commit()
    return _out(ctx, q)


@router.post("/{quotation_id}/submit", response_model=QuotationOut)
def submit(quotation_id: UUID, ctx: TenantContext = Depends(require("quotations:write"))):
    q = get_quotation_scoped(ctx, quotation_id)
    submit_for_approval(ctx, q)
    record_audit(ctx, "quotation.submit", "quotation", q.id, {})
    ctx.db.commit()
    return _out(ctx, q)


@router.post("/{quotation_id}/approve", response_model=QuotationOut)
def approve(quotation_id: UUID, body: ApproveIn,
            ctx: TenantContext = Depends(require("quotations:approve"))):
    q = get_quotation_scoped(ctx, quotation_id)
    approve_quotation(ctx, q, body.comment)
    record_audit(ctx, "quotation.approve", "quotation", q.id, {"comment": body.comment})
    ctx.db.commit()
    return _out(ctx, q)


@router.post("/{quotation_id}/reject", response_model=QuotationOut)
def reject(quotation_id: UUID, body: ApproveIn,
           ctx: TenantContext = Depends(require("quotations:approve"))):
    q = get_quotation_scoped(ctx, quotation_id)
    transition_quotation(ctx, q, "REJECTED", ctx.role)
    record_audit(ctx, "quotation.reject", "quotation", q.id, {"comment": body.comment})
    ctx.db.commit()
    return _out(ctx, q)


@router.post("/{quotation_id}/convert", status_code=201)
def convert(quotation_id: UUID, ctx: TenantContext = Depends(require("sales_orders:write"))):
    q = get_quotation_scoped(ctx, quotation_id)
    so = convert_to_sales_order(ctx, q)
    record_audit(ctx, "quotation.convert", "sales_order", so.id,
                 {"after": {"number": so.number, "quotation_id": str(q.id)}})
    ctx.db.commit()
    from app.api.sales_orders import sales_order_out
    return sales_order_out(ctx, so)


@router.get("/{quotation_id}/export", response_class=HTMLResponse)
def export_pdf_html(quotation_id: UUID, ctx: TenantContext = Depends(require("read"))):
    """Customer-facing quotation document (printable HTML → browser PDF). Internal costs excluded."""
    q = get_quotation_scoped(ctx, quotation_id)
    version = _current_version(ctx, q)
    items = ctx.db.scalars(select(QuotationItem).where(
        QuotationItem.quotation_version_id == version.id)).all()
    return HTMLResponse(build_quotation_pdf_html(ctx, q, version, items))
