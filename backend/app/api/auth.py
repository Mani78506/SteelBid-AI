from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.deps import (clear_session_cookie, get_current_session, get_tenant,
                           session_expiry, set_session_cookie)
from app.core.errors import ApiError, not_found
from app.core.security import hash_token, new_session_token, verify_password
from app.database import get_db
from app.models.identity import Membership, Organization, Session, User
from app.schemas.auth import LoginIn, MeOut, SwitchOrgIn
from app.schemas.common import MembershipOut, OrganizationOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: OrmSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        # uniform failure — do not reveal which part failed
        raise ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    token = new_session_token()
    # default active org = first membership
    first_org = db.scalar(
        select(Membership.organization_id).where(Membership.user_id == user.id).limit(1))
    sess = Session(
        token_hash=hash_token(token), user_id=user.id, active_organization_id=first_org,
        expires_at=session_expiry(), ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512])
    db.add(sess)
    db.commit()
    set_session_cookie(response, token)
    return {"ok": True, "user": UserOut.model_validate(user).model_dump(mode="json")}


@router.post("/logout", status_code=204)
def logout(response: Response, db: OrmSession = Depends(get_db),
           sess: Session = Depends(get_current_session)):
    db.delete(sess)
    db.commit()
    clear_session_cookie(response)


@router.post("/refresh")
def refresh(response: Response, db: OrmSession = Depends(get_db),
            sess: Session = Depends(get_current_session)):
    sess.expires_at = session_expiry()
    db.commit()
    return {"ok": True, "expires_at": sess.expires_at.isoformat()}


@router.get("/me", response_model=MeOut)
def me(db: OrmSession = Depends(get_db), sess: Session = Depends(get_current_session)):
    user = db.get(User, sess.user_id)
    memberships = db.scalars(
        select(Membership).where(Membership.user_id == user.id).join(Organization)).all()
    active_org = db.get(Organization, sess.active_organization_id) if sess.active_organization_id else None
    active_role = next(
        (m.role for m in memberships if active_org and m.organization_id == active_org.id), None)
    return MeOut(
        user=UserOut.model_validate(user),
        active_organization=OrganizationOut.model_validate(active_org) if active_org else None,
        role=active_role,
        memberships=[MembershipOut.model_validate(m) for m in memberships])


@router.get("/organizations", response_model=list[OrganizationOut])
def organizations(db: OrmSession = Depends(get_db), sess: Session = Depends(get_current_session)):
    orgs = db.scalars(
        select(Organization).join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == sess.user_id, Organization.is_active.is_(True))).all()
    return [OrganizationOut.model_validate(o) for o in orgs]


@router.post("/switch-organization")
def switch_organization(body: SwitchOrgIn, db: OrmSession = Depends(get_db),
                        sess: Session = Depends(get_current_session)):
    membership = db.scalar(
        select(Membership).where(Membership.organization_id == body.organization_id,
                                 Membership.user_id == sess.user_id))
    if membership is None:
        raise not_found("Organization")  # never reveal org existence across tenancy boundary
    org = db.get(Organization, body.organization_id)
    if org is None or not org.is_active:
        raise ApiError(403, "ORGANIZATION_INACTIVE", "Organization is not active")
    sess.active_organization_id = org.id
    db.commit()
    return {"ok": True, "organization": OrganizationOut.model_validate(org).model_dump(mode="json"),
            "role": membership.role}
