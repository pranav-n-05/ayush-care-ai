import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import PermissionDenied
from app.core.schemas import ERROR_RESPONSES
from app.db.session import get_db
from app.modules.identity import service
from app.modules.identity.access import (
    OrgContext,
    Principal,
    get_principal,
    load_org_context,
    require,
    require_platform_admin,
)
from app.modules.identity.models import OrganizationMembership, User
from app.modules.identity.permissions import P
from app.modules.identity.schemas import (
    AcceptInvitationRequest,
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    InviteRequest,
    InviteResponse,
    LoginRequest,
    LoginResponse,
    MemberOut,
    MembershipOut,
    MeResponse,
    RevokedResponse,
    SetActiveRequest,
    SetRolesRequest,
    SwitchOrganizationRequest,
)

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    max_age = s.session_absolute_ttl_minutes * 60
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
    )
    # Readable by the SPA so it can echo the value in X-CSRF-Token (double-submit, but the
    # server validates against the hash bound to the session, not against the cookie).
    response.set_cookie(
        s.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(
    body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    issued = await service.login(db, body.email, body.password)
    _set_cookies(response, issued.token, issued.csrf_token)
    active_org = None
    if issued.session.active_membership_id:
        m = await db.get(OrganizationMembership, issued.session.active_membership_id)
        active_org = m.organization_id if m else None
    return LoginResponse(
        csrf_token=issued.csrf_token,
        expires_at=issued.session.expires_at,
        active_organization_id=active_org,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await service.logout(db, principal.session)
    _clear_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/auth/sessions/revoke-others", response_model=RevokedResponse, tags=["auth"])
async def revoke_others(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> RevokedResponse:
    return RevokedResponse(revoked=await service.revoke_other_sessions(db, principal.session))


@router.post("/auth/active-organization", response_model=MeResponse, tags=["auth"])
async def switch_org(
    body: SwitchOrganizationRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    await service.switch_organization(db, principal.session, body.organization_id)
    return await _me(db, principal)


@router.post("/auth/invitations/accept", status_code=201, tags=["auth"])
async def accept_invitation(
    body: AcceptInvitationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    await service.accept_invitation(db, body.token, body.password)
    return {"status": "accepted"}


async def _me(db: AsyncSession, principal: Principal) -> MeResponse:
    memberships = await service.list_memberships(db, principal.user.id)
    perms: list[str] = []
    active_org = None
    if principal.session.active_membership_id:
        try:
            ctx = await load_org_context(db, principal)
            perms, active_org = sorted(ctx.permissions), ctx.organization_id
        except PermissionDenied:  # inactive membership simply yields no permissions
            perms, active_org = [], None
    return MeResponse(
        id=principal.user.id,
        email=principal.user.email,
        full_name=principal.user.full_name,
        is_platform_admin=principal.user.is_platform_admin,
        memberships=[
            MembershipOut(
                membership_id=m.id,
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                roles=sorted(r.code for r in m.roles),
            )
            for m in memberships
        ],
        active_organization_id=active_org,
        permissions=perms,
    )


@router.get("/users/me", response_model=MeResponse, tags=["auth"])
async def me(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    return await _me(db, principal)


@router.post(
    "/platform/organizations",
    response_model=CreateOrganizationResponse,
    status_code=201,
    tags=["platform"],
)
async def create_org(
    body: CreateOrganizationRequest,
    principal: Principal = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> CreateOrganizationResponse:
    org, token = await service.create_organization(
        db,
        actor=principal.user,
        name=body.name,
        slug=body.slug,
        admin_email=body.admin_email,
        admin_full_name=body.admin_full_name,
    )
    return CreateOrganizationResponse(organization_id=org.id, admin_invitation_token=token)


def _member_out(m: OrganizationMembership) -> MemberOut:
    return MemberOut(
        membership_id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        roles=sorted(r.code for r in m.roles),
        is_active=m.is_active,
    )


@router.get("/organization/members", response_model=list[MemberOut], tags=["organization"])
async def members(
    ctx: OrgContext = Depends(require(P.ORG_VIEW_MEMBERS)), db: AsyncSession = Depends(get_db)
) -> list[MemberOut]:
    return [_member_out(m) for m in await service.list_members(db, ctx.organization_id)]


@router.post(
    "/organization/invitations",
    response_model=InviteResponse,
    status_code=201,
    tags=["organization"],
)
async def invite(
    body: InviteRequest,
    ctx: OrgContext = Depends(require(P.ORG_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    inviter = await db.get(User, ctx.user_id)
    assert inviter is not None
    token = await service.invite_member(
        db,
        org_id=ctx.organization_id,
        inviter=inviter,
        email=body.email,
        full_name=body.full_name,
        role_code=body.role_code,
    )
    return InviteResponse(invitation_token=token)


@router.put(
    "/organization/members/{membership_id}/roles", response_model=MemberOut, tags=["organization"]
)
async def set_roles(
    membership_id: uuid.UUID,
    body: SetRolesRequest,
    ctx: OrgContext = Depends(require(P.ORG_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    m = await service.set_member_roles(
        db,
        org_id=ctx.organization_id,
        actor_membership_id=ctx.membership_id,
        actor_user_id=ctx.user_id,
        membership_id=membership_id,
        role_codes=body.role_codes,
    )
    return _member_out(m)


@router.put(
    "/organization/members/{membership_id}/active", response_model=MemberOut, tags=["organization"]
)
async def set_active(
    membership_id: uuid.UUID,
    body: SetActiveRequest,
    ctx: OrgContext = Depends(require(P.ORG_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    m = await service.set_member_active(
        db,
        org_id=ctx.organization_id,
        actor_membership_id=ctx.membership_id,
        actor_user_id=ctx.user_id,
        membership_id=membership_id,
        active=body.is_active,
    )
    return _member_out(m)
