import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, Timestamps, UUIDPk


class FollowUpTask(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"], ["patients.organization_id", "patients.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        CheckConstraint("status IN ('scheduled','completed','cancelled')", name="status"),
        CheckConstraint("channel IN ('sms','email','phone_call')", name="channel"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(50), nullable=False, default="follow_up_visit")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class Notification(UUIDPk, TenantOwned, Timestamps, Base):
    """Reminder delivery record. Message bodies are generic templates with no clinical detail."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        ForeignKeyConstraint(
            ["organization_id", "follow_up_task_id"],
            ["follow_up_tasks.organization_id", "follow_up_tasks.id"],
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed','skipped_no_consent','skipped_no_contact')",
            name="status",
        ),
    )
    follow_up_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template_code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider: Mapped[str | None] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
