import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, Timestamps, UUIDPk


class Encounter(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"], ["patients.organization_id", "patients.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "clinic_id"], ["clinics.organization_id", "clinics.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "practitioner_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
        ),
        CheckConstraint("status IN ('open','in_review','closed')", name="status"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    practitioner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    visit_reason: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
