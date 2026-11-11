import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.core.schemas import APIModel


class LoginRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(APIModel):
    csrf_token: str
    expires_at: datetime
    active_organization_id: uuid.UUID | None


class MembershipOut(APIModel):
    membership_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    roles: list[str]


class MeResponse(APIModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_platform_admin: bool
    memberships: list[MembershipOut]
    active_organization_id: uuid.UUID | None
    permissions: list[str]


class SwitchOrganizationRequest(APIModel):
    organization_id: uuid.UUID


class CreateOrganizationRequest(APIModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=3, max_length=62)
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=200)


class CreateOrganizationResponse(APIModel):
    organization_id: uuid.UUID
    admin_invitation_token: str = Field(
        description="Shown once. Deliver out-of-band; only its hash is stored."
    )


class InviteRequest(APIModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role_code: str


class InviteResponse(APIModel):
    invitation_token: str


class AcceptInvitationRequest(APIModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class MemberOut(APIModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    is_active: bool


class SetRolesRequest(APIModel):
    role_codes: list[str]


class SetActiveRequest(APIModel):
    is_active: bool


class RevokedResponse(APIModel):
    revoked: int
