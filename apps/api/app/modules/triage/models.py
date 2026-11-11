"""Deterministic, versioned red-flag rules. An LLM never decides emergency status.

Rule versions marked `demo_only` are illustrative examples written without clinical review;
the database forbids enabling them for clinical use."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantOwned, Timestamps, UUIDPk


class TriageRule(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "triage_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class TriageRuleVersion(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "triage_rule_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("rule_id", "version_number"),
        ForeignKeyConstraint(
            ["organization_id", "rule_id"], ["triage_rules.organization_id", "triage_rules.id"]
        ),
        CheckConstraint("status IN ('demo_only','approved','retired')", name="status"),
        CheckConstraint(
            "NOT (status = 'demo_only' AND clinical_use_enabled)", name="demo_never_clinical"
        ),
        CheckConstraint(
            "NOT clinical_use_enabled OR approved_by_user_id IS NOT NULL", name="approval_required"
        ),
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)  # reviewer-defined label
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="demo_only")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    clinical_use_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TriageEvent(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "triage_events"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "intake_answer_id"),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_version_id"],
            ["triage_rule_versions.organization_id", "triage_rule_versions.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "intake_answer_id"],
            ["intake_answers.organization_id", "intake_answers.id"],
        ),
        CheckConstraint("status IN ('open','acknowledged','escalated','resolved')", name="status"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    intake_answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    answer_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    is_demo_rule: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_code: Mapped[str | None] = mapped_column(String(50))
