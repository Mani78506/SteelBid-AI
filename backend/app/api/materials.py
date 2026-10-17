from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core.deps import TenantContext, require
from app.core.errors import conflict, not_found
from app.core.pagination import Page, PageParams, apply_sort, paginate
from app.models.materials import MaterialCatalog, OrganizationMaterial
from app.schemas.materials import AvailabilityOut, MaterialIn, MaterialOut, MaterialUpdate
from app.services.audit import record_audit
from app.services.inventory import material_availability

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/catalog", response_model=Page[dict])
def list_catalog(ctx: TenantContext = Depends(require("read")),
                 params: PageParams = Depends(), search: str | None = Query(None)):
    stmt = select(MaterialCatalog)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(MaterialCatalog.sku.ilike(like),
                              MaterialCatalog.name.ilike(like),
                              MaterialCatalog.grade.ilike(like)))
    stmt = stmt.order_by(MaterialCatalog.sku)
    rows, total = paginate(ctx.db, stmt, params)
    items = [{"id": str(r.id), "sku": r.sku, "name": r.name, "form": r.form, "grade": r.grade,
              "standard": r.standard, "density": r.density and str(r.density),
              "base_unit": r.base_unit} for r in rows]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("", response_model=Page[MaterialOut])
def list_materials(ctx: TenantContext = Depends(require("read")),
                   params: PageParams = Depends(), search: str | None = Query(None),
                   form: str | None = Query(None), grade: str | None = Query(None),
                   is_active: bool | None = Query(None)):
    stmt = select(OrganizationMaterial).where(OrganizationMaterial.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(OrganizationMaterial.sku.ilike(like),
                              OrganizationMaterial.name.ilike(like)))
    if form:
        stmt = stmt.where(OrganizationMaterial.form == form)
    if grade:
        stmt = stmt.where(OrganizationMaterial.grade == grade)
    if is_active is not None:
        stmt = stmt.where(OrganizationMaterial.is_active.is_(is_active))
    stmt = apply_sort(stmt, params.sort, {"sku": OrganizationMaterial.sku,
                                          "name": OrganizationMaterial.name,
                                          "created_at": OrganizationMaterial.created_at},
                      OrganizationMaterial.sku)
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[MaterialOut.model_validate(r) for r in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(body: MaterialIn, ctx: TenantContext = Depends(require("materials:write"))):
    exists = ctx.db.scalar(select(OrganizationMaterial.id).where(
        OrganizationMaterial.organization_id == ctx.org_id, OrganizationMaterial.sku == body.sku))
    if exists:
        raise conflict("DUPLICATE_SKU", f"SKU '{body.sku}' already exists in this organization")
    m = OrganizationMaterial(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(m)
    ctx.db.flush()
    record_audit(ctx, "material.create", "organization_material", m.id,
                 {"after": body.model_dump()})
    ctx.db.commit()
    return MaterialOut.model_validate(m)


@router.get("/availability", response_model=list[AvailabilityOut])
def availability(ctx: TenantContext = Depends(require("read")),
                 warehouse_id: UUID | None = Query(None),
                 material_id: UUID | None = Query(None)):
    stmt = select(OrganizationMaterial).where(
        OrganizationMaterial.organization_id == ctx.org_id,
        OrganizationMaterial.is_active.is_(True))
    if material_id:
        stmt = stmt.where(OrganizationMaterial.id == material_id)
    mats = ctx.db.scalars(stmt.order_by(OrganizationMaterial.sku)).all()
    out = []
    for m in mats:
        a = material_availability(None, ctx.db, ctx.org_id, m.id, warehouse_id)
        out.append(AvailabilityOut(
            material_id=m.id, sku=m.sku, name=m.name, **a,
            low_stock_threshold=m.low_stock_threshold,
            is_low=bool(m.low_stock_threshold is not None
                        and a["available"] < m.low_stock_threshold)))
    return out


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(material_id: UUID, ctx: TenantContext = Depends(require("read"))):
    m = ctx.db.scalar(select(OrganizationMaterial).where(
        OrganizationMaterial.id == material_id, OrganizationMaterial.organization_id == ctx.org_id))
    if m is None:
        raise not_found("Material")
    return MaterialOut.model_validate(m)


@router.patch("/{material_id}", response_model=MaterialOut)
def update_material(material_id: UUID, body: MaterialUpdate,
                    ctx: TenantContext = Depends(require("materials:write"))):
    m = ctx.db.scalar(select(OrganizationMaterial).where(
        OrganizationMaterial.id == material_id, OrganizationMaterial.organization_id == ctx.org_id))
    if m is None:
        raise not_found("Material")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(m, k) for k in changes}
    for k, v in changes.items():
        setattr(m, k, v)
    record_audit(ctx, "material.update", "organization_material", m.id,
                 {"before": before, "after": changes})
    ctx.db.commit()
    return MaterialOut.model_validate(m)
