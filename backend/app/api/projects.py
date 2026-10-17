from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.calc.finance import ZERO, q_money
from app.core.deps import TenantContext, require
from app.core.errors import not_found
from app.core.pagination import Page, PageParams, paginate
from app.models.materials import OrganizationMaterial
from app.models.projects import Project, ProjectRequirement
from app.schemas.projects import (ProjectIn, ProjectOut, RequirementIn, RequirementOut)
from app.services.audit import record_audit

router = APIRouter(prefix="/projects", tags=["projects"])


def _p_out(p: Project) -> ProjectOut:
    return ProjectOut.model_validate(p)


@router.get("", response_model=Page[ProjectOut])
def list_projects(ctx: TenantContext = Depends(require("read")),
                  params: PageParams = Depends(), search: str | None = Query(None),
                  status: str | None = Query(None), project_type: str | None = Query(None)):
    stmt = select(Project).where(Project.organization_id == ctx.org_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((Project.code.ilike(like)) | (Project.name.ilike(like)))
    if status:
        stmt = stmt.where(Project.status == status)
    if project_type:
        stmt = stmt.where(Project.project_type == project_type)
    stmt = stmt.order_by(Project.created_at.desc())
    rows, total = paginate(ctx.db, stmt, params)
    return Page(items=[_p_out(p) for p in rows], total=total,
                page=params.page, page_size=params.page_size)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, ctx: TenantContext = Depends(require("projects:write"))):
    valid_types = {"RAILWAY", "BRIDGE", "BUILDING", "INDUSTRIAL", "FABRICATION"}
    if body.project_type not in valid_types:
        from app.core.errors import bad_request
        raise bad_request("INVALID_PROJECT_TYPE", f"project_type must be one of {sorted(valid_types)}")
    p = Project(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(p)
    ctx.db.flush()
    record_audit(ctx, "project.create", "project", p.id, {"after": body.model_dump()})
    ctx.db.commit()
    return _p_out(p)


def _get_project(ctx: TenantContext, project_id: UUID) -> Project:
    p = ctx.db.scalar(select(Project).where(Project.id == project_id,
                                            Project.organization_id == ctx.org_id))
    if p is None:
        raise not_found("Project")
    return p


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, ctx: TenantContext = Depends(require("read"))):
    return _p_out(_get_project(ctx, project_id))


@router.get("/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project_id: UUID, ctx: TenantContext = Depends(require("read"))):
    _get_project(ctx, project_id)
    rows = ctx.db.scalars(select(ProjectRequirement).where(
        ProjectRequirement.project_id == project_id,
        ProjectRequirement.organization_id == ctx.org_id)).all()
    out = []
    for r in rows:
        ro = RequirementOut.model_validate(r)
        m = ctx.db.get(OrganizationMaterial, r.material_id)
        ro.material_name = m.name if m else None
        out.append(ro)
    return out


@router.post("/{project_id}/requirements", response_model=RequirementOut, status_code=201)
def add_requirement(project_id: UUID, body: RequirementIn,
                    ctx: TenantContext = Depends(require("projects:write"))):
    _get_project(ctx, project_id)
    mat = ctx.db.get(OrganizationMaterial, body.material_id)
    if mat is None or mat.organization_id != ctx.org_id:
        raise not_found("Material")
    r = ProjectRequirement(organization_id=ctx.org_id, project_id=project_id, **body.model_dump())
    ctx.db.add(r)
    ctx.db.flush()
    record_audit(ctx, "project.add_requirement", "project_requirement", r.id,
                 {"after": body.model_dump()})
    ctx.db.commit()
    ro = RequirementOut.model_validate(r)
    ro.material_name = mat.name
    return ro
