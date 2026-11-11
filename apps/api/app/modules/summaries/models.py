"""AI-drafted clinical summaries. Every version is immutable; edits create a new version.
Approval binds a practitioner to one specific version and its source snapshot."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk


class ClinicalSummary(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "clinical_summaries"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "encounter_id"),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        CheckConstraint("status IN ('draft','approved')", name="status"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_version_number: Mapped[int | None] = mapped_column(Integer)


class SummaryVersion(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "summary_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("summary_id", "version_number"),
        ForeignKeyConstraint(
            ["organization_id", "summary_id"],
            ["clinical_summaries.organization_id", "clinical_summaries.id"],
        ),
        CheckConstraint("origin IN ('ai_draft','practitioner_edit')", name="origin"),
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class SummaryApproval(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "summary_approvals"
    __table_args__ = (
        UniqueConstraint("summary_version_id"),
        ForeignKeyConstraint(
            ["organization_id", "summary_version_id"],
            ["summary_versions.organization_id", "summary_versions.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by_membership_id"],
            ["organization_memberships.organization_id", "organization_memberships.id"],
        ),
    )
    summary_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_by_membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attestation: Mapped[str] = mapped_column(String(300), nullable=False)


class SummaryJob(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "summary_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "encounter_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="status"),
        CheckConstraint("attempts <= max_attempts", name="bounded_attempts"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    summary_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary_version_number: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
