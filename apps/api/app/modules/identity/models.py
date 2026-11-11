"""Organizations, clinics, global user identity, tenant-scoped memberships and sessions.

Global identity (users) is separate from organization membership. Staff roles attach to a
membership, never to the user directly, so a role in one organization grants nothing in
another. `users.is_platform_admin` grants platform operations only (creating organizations,
bootstrapping their first administrator); it grants no clinical-record permissions.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # External AI providers may only receive data when this is true AND processing terms,
    # security controls and legal review are documented. No external provider exists yet.
    external_ai_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Clinic(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "clinics"
    __table_args__ = (UniqueConstraint("organization_id", "id"),)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDPk, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)


class Role(UUIDPk, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )


membership_roles = Table(
    "membership_roles",
    Base.metadata,
    Column(
        "membership_id",
        ForeignKey("organization_memberships.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)


class OrganizationMembership(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        UniqueConstraint("organization_id", "id"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    roles: Mapped[list[Role]] = relationship(secondary=membership_roles, lazy="selectin")
    user: Mapped[User] = relationship(lazy="joined")
    organization: Mapped[Organization] = relationship(lazy="joined")


class UserSession(UUIDPk, CreatedAt, Base):
    """Opaque server-side session. Only SHA-256 hashes of the session and CSRF tokens are
    stored, so a database read does not yield usable credentials."""

    __tablename__ = "sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    active_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization_memberships.id", ondelete="SET NULL")
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(50))


class Invitation(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "invitations"
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PasswordResetToken(UUIDPk, CreatedAt, Base):
    """Schema only. The reset flow is NOT implemented (no email provider); see docs/progress.md."""

    __tablename__ = "password_reset_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientUserLink(UUIDPk, TenantOwned, CreatedAt, Base):
    """Explicit linkage between a patient-role user and exactly one patient record."""

    __tablename__ = "patient_user_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"],
            ["patients.organization_id", "patients.id"],
            ondelete="RESTRICT",
        ),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
