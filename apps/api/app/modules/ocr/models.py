"""OCR jobs and extracted entities. Extracted values are UNVERIFIED until an authorized
reviewer verifies or corrects them; only verified/corrected entities may feed summaries."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk

JOB_STATUSES = ("queued", "running", "succeeded", "failed")


class OCRJob(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "document_version_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
        ),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="status"),
        CheckConstraint("attempts <= max_attempts", name="bounded_attempts"),
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    provider: Mapped[str | None] = mapped_column(String(80))
    provider_version: Mapped[str | None] = mapped_column(String(40))
    failure_reason: Mapped[str | None] = mapped_column(String(200))  # safe for users
    result_text: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedEntity(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "extracted_entities"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "ocr_job_id"], ["ocr_jobs.organization_id", "ocr_jobs.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
        ),
        CheckConstraint(
            "entity_type IN ('medication','allergy','lab_result','condition_mentioned','other')",
            name="type",
        ),
        CheckConstraint(
            "verification_status IN ('unverified','verified','corrected','rejected')",
            name="verification",
        ),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="conf"),
        Index("ix_extracted_entities_lineage", "lineage_id", "revision", unique=True),
    )
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # All revisions of the same extracted fact share a lineage_id.
    lineage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    page: Mapped[int | None] = mapped_column(Integer)
    line: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    # Only populated when the OCR provider actually reports one. Never invented.
    confidence: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
