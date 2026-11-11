"""Versioned questionnaires, intake sessions and revisioned answers.

A published questionnaire version is immutable. Each intake session is pinned to one
published version. Answers are append-only revisions: correcting an answer inserts a new
row and flips `is_current` on the previous one, so the original response is preserved.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk


class QuestionnaireTemplate(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "questionnaire_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


class QuestionnaireVersion(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "questionnaire_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("template_id", "version_number"),
        ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["questionnaire_templates.organization_id", "questionnaire_templates.id"],
        ),
        CheckConstraint("status IN ('draft','published','retired')", name="status"),
        CheckConstraint(
            "clinical_review_status IN ('demo_unreviewed','practitioner_reviewed')",
            name="review_status",
        ),
    )
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    clinical_review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="demo_unreviewed"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


class Question(UUIDPk, TenantOwned, Base):
    """Materialized from a version's definition at publish time."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("questionnaire_version_id", "code"),
        ForeignKeyConstraint(
            ["organization_id", "questionnaire_version_id"],
            ["questionnaire_versions.organization_id", "questionnaire_versions.id"],
        ),
    )
    questionnaire_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    respondent: Mapped[str] = mapped_column(String(20), nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class IntakeSession(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "intake_sessions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "questionnaire_version_id"],
            ["questionnaire_versions.organization_id", "questionnaire_versions.id"],
        ),
        CheckConstraint("status IN ('in_progress','submitted','reviewed')", name="status"),
        CheckConstraint("language IN ('en','hi','ta')", name="language"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    questionnaire_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    started_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )


ANSWER_STATUSES = ("answered", "unknown", "declined", "not_applicable")


class IntakeAnswer(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "intake_answers"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("intake_session_id", "question_id", "revision"),
        Index(
            "uq_intake_answers_current",
            "intake_session_id",
            "question_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        ForeignKeyConstraint(
            ["organization_id", "intake_session_id"],
            ["intake_sessions.organization_id", "intake_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "question_id"], ["questions.organization_id", "questions.id"]
        ),
        CheckConstraint(
            "answer_status IN ('answered','unknown','declined','not_applicable')",
            name="answer_status",
        ),
        CheckConstraint(
            "(answer_status = 'answered') = (value IS NOT NULL)", name="value_iff_answered"
        ),
        CheckConstraint(
            "source IN ('patient_reported','staff_entered','practitioner_observed')", name="source"
        ),
        CheckConstraint(
            "translation_status IN ('not_required','translation_pending','draft_requires_review','reviewed')",
            name="translation_status",
        ),
    )
    intake_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    answer_status: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    original_language: Mapped[str] = mapped_column(String(5), nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text)
    translated_text_en: Mapped[str | None] = mapped_column(Text)
    translation_provider: Mapped[str | None] = mapped_column(String(80))
    translation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="not_required"
    )
    entered_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    change_reason: Mapped[str | None] = mapped_column(String(200))
