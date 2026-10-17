from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.crm import Customer, CustomerContact, CustomerInquiry, InquiryItem
from app.schemas.crm import (ContactIn, ContactOut, CustomerIn, CustomerOut, CustomerUpdate,
                             InquiryIn, InquiryOut, InquiryStatusIn)
from app.services.audit import record_audit

router = APIRouter(tags=["customers"])


def _customer_out(c: Customer) -> CustomerOut:
    return CustomerOut.model_validate(c)


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(ctx: TenantContext = Depends(require("read")),
                   params: PageParams = Depends(), search: str | None = Query(None),
                   is_active: bool | None = Query(None)):
    stmt = select(Customer).where(Customer.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.code.ilike(like),
                              Customer.gstin.ilike(like)))
    if is_active is not None:
        stmt = stmt.where(Customer.is_active.is_(is_active))
    stmt = apply_sort(stmt, params.sort, {"name": Customer.name, "code": Customer.code,
                                          "created_at": Customer.created_at}, Customer.name)
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_customer_out(c) for c in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, ctx: TenantContext = Depends(require("customers:write"))):
    exists = ctx.db.scalar(select(Customer.id).where(Customer.organization_id == ctx.org_id,
                                                     Customer.code == body.code))
    if exists:
        raise conflict("DUPLICATE_CODE", f"Customer code '{body.code}' already exists")
    c = Customer(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    record_audit(ctx, "customer.create", "customer", c.id, {"after": body.model_dump()})
    ctx.db.commit()
    return _customer_out(c)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: UUID, ctx: TenantContext = Depends(require("read"))):
    c = ctx.db.scalar(select(Customer).where(Customer.id == customer_id,
                                             Customer.organization_id == ctx.org_id))
    if c is None:
        raise not_found("Customer")
    return _customer_out(c)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: UUID, body: CustomerUpdate,
                    ctx: TenantContext = Depends(require("customers:write"))):
    c = ctx.db.scalar(select(Customer).where(Customer.id == customer_id,
                                             Customer.organization_id == ctx.org_id))
    if c is None:
        raise not_found("Customer")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(c, k) for k in changes}
    for k, v in changes.items():
        setattr(c, k, v)
    record_audit(ctx, "customer.update", "customer", c.id, {"before": before, "after": changes})
    ctx.db.commit()
    return _customer_out(c)


@router.get("/customers/{customer_id}/contacts", response_model=list[ContactOut])
def list_contacts(customer_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _ = get_customer(customer_id, ctx)
    rows = ctx.db.scalars(select(CustomerContact).where(
        CustomerContact.customer_id == customer_id,
        CustomerContact.organization_id == ctx.org_id)).all()
    return [ContactOut.model_validate(r) for r in rows]


@router.post("/customers/{customer_id}/contacts", response_model=ContactOut, status_code=201)
def add_contact(customer_id: UUID, body: ContactIn,
                ctx: TenantContext = Depends(require("customers:write"))):
    _ = get_customer(customer_id, ctx)
    contact = CustomerContact(organization_id=ctx.org_id, customer_id=customer_id, **body.model_dump())
    ctx.db.add(contact)
    ctx.db.flush()
    record_audit(ctx, "customer.add_contact", "customer", customer_id, {"after": body.model_dump()})
    ctx.db.commit()
    return ContactOut.model_validate(contact)


# ---------------- Inquiries ----------------
def _inquiry_out(ctx: TenantContext, i: CustomerInquiry) -> InquiryOut:
    from app.models.materials import OrganizationMaterial
    from app.schemas.crm import InquiryItemOut
    customer = ctx.db.get(Customer, i.customer_id)
    items = ctx.db.scalars(select(InquiryItem).where(InquiryItem.inquiry_id == i.id)).all()
    mat_names = {}
    for it in items:
        if it.material_id and it.material_id not in mat_names:
            m = ctx.db.get(OrganizationMaterial, it.material_id)
            mat_names[it.material_id] = m.name if m else None
    out = InquiryOut.model_validate(i)
    out.customer_name = customer.name if customer else None
    item_outs = []
    for it in items:
        io = InquiryItemOut.model_validate(it)
        io.material_name = mat_names.get(it.material_id)
        item_outs.append(io)
    out.items = item_outs
    return out


@router.get("/inquiries", response_model=Page[InquiryOut])
def list_inquiries(ctx: TenantContext = Depends(require("read")),
                   params: PageParams = Depends(), search: str | None = Query(None),
                   status: str | None = Query(None), customer_id: UUID | None = Query(None)):
    stmt = select(CustomerInquiry).where(CustomerInquiry.organization_id == ctx.org_id)
    if search:
        stmt = stmt.where(CustomerInquiry.reference.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(CustomerInquiry.status == status)
    if customer_id:
        stmt = stmt.where(CustomerInquiry.customer_id == customer_id)
    stmt = apply_sort(stmt, params.sort, {"received_at": CustomerInquiry.received_at,
                                          "reference": CustomerInquiry.reference},
                      CustomerInquiry.received_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_inquiry_out(ctx, i) for i in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("/inquiries", response_model=InquiryOut, status_code=201)
def create_inquiry(body: InquiryIn, ctx: TenantContext = Depends(require("inquiries:write"))):
    customer = ctx.db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                    Customer.organization_id == ctx.org_id))
    if customer is None:
        raise not_found("Customer")
    exists = ctx.db.scalar(select(CustomerInquiry.id).where(
        CustomerInquiry.organization_id == ctx.org_id, CustomerInquiry.reference == body.reference))
    if exists:
        raise conflict("DUPLICATE_REFERENCE", f"Inquiry reference '{body.reference}' already exists")
    inquiry = CustomerInquiry(
        organization_id=ctx.org_id, customer_id=body.customer_id, reference=body.reference,
        source=body.source, required_by=body.required_by, notes=body.notes)
    ctx.db.add(inquiry)
    ctx.db.flush()
    from app.models.materials import OrganizationMaterial
    for item_in in body.items:
        if item_in.material_id:
            mat = ctx.db.get(OrganizationMaterial, item_in.material_id)
            if mat is None or mat.organization_id != ctx.org_id:
                raise not_found("Material")
        ctx.db.add(InquiryItem(organization_id=ctx.org_id, inquiry_id=inquiry.id,
                               **item_in.model_dump()))
    record_audit(ctx, "inquiry.create", "customer_inquiry", inquiry.id,
                 {"after": {"reference": body.reference, "items": len(body.items)}})
    ctx.db.commit()
    return _inquiry_out(ctx, inquiry)


@router.get("/inquiries/{inquiry_id}", response_model=InquiryOut)
def get_inquiry(inquiry_id: UUID, ctx: TenantContext = Depends(require("read"))):
    i = ctx.db.scalar(select(CustomerInquiry).where(CustomerInquiry.id == inquiry_id,
                                                    CustomerInquiry.organization_id == ctx.org_id))
    if i is None:
        raise not_found("Inquiry")
    return _inquiry_out(ctx, i)


@router.patch("/inquiries/{inquiry_id}/status", response_model=InquiryOut)
def set_inquiry_status(inquiry_id: UUID, body: InquiryStatusIn,
                       ctx: TenantContext = Depends(require("inquiries:write"))):
    i = ctx.db.scalar(select(CustomerInquiry).where(CustomerInquiry.id == inquiry_id,
                                                    CustomerInquiry.organization_id == ctx.org_id))
    if i is None:
        raise not_found("Inquiry")
    before = i.status
    i.status = body.status
    record_audit(ctx, "inquiry.status", "customer_inquiry", i.id,
                 {"before": {"status": before}, "after": {"status": body.status}})
    ctx.db.commit()
    return _inquiry_out(ctx, i)


@router.get("/inquiries-stats/count-by-status")
def inquiry_counts(ctx: TenantContext = Depends(require("read"))):
    rows = ctx.db.execute(
        select(CustomerInquiry.status, func.count()).where(
            CustomerInquiry.organization_id == ctx.org_id).group_by(CustomerInquiry.status)).all()
    return {status: count for status, count in rows}
