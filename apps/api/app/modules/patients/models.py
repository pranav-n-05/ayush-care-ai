"""Patients, identifiers and consent. Patients are never hard-deleted (no cascade of clinical
history); deactivation is the only removal path until a reviewed retention policy exists."""

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk


class Patient(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "record_number"),
        CheckConstraint(
            "birth_date IS NOT NULL OR (age_years IS NOT NULL AND age_recorded_on IS NOT NULL)",
            name="birth_date_or_age",
        ),
        CheckConstraint(
            "birth_date_precision IN ('exact','year','estimated_from_age')", name="precision"
        ),
        CheckConstraint(
            "sex_for_clinical_use IN ('female','male','intersex','unknown')", name="sex"
        ),
        CheckConstraint("preferred_language IN ('en','hi','ta')", name="language"),
        Index("ix_patients_org_family_given", "organization_id", "family_name", "given_name"),
        Index("ix_patients_org_phone", "organization_id", "phone"),
    )
    record_number: Mapped[str] = mapped_column(String(20), nullable=False)
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_date_precision: Mapped[str] = mapped_column(String(20), nullable=False)
    age_years: Mapped[int | None] = mapped_column(Integer)
    age_recorded_on: Mapped[date | None] = mapped_column(Date)
    sex_for_clinical_use: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(320))
    address_line: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(12))
    preferred_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20))
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    __mapper_args__ = {"version_id_col": lock_version}


class PatientIdentifier(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "patient_identifiers"
    __table_args__ = (
        UniqueConstraint("organization_id", "system", "value"),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"], ["patients.organization_id", "patients.id"]
        ),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    system: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)


CONSENT_TYPES = ("data_processing", "ai_assisted_documentation", "contact_reminders")
CONSENT_STATUSES = ("granted", "withdrawn")


class ConsentRecord(UUIDPk, TenantOwned, Timestamps, Base):
    """Current consent state per (patient, type). History lives in consent_events."""

    __tablename__ = "consent_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "patient_id", "consent_type"),
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"], ["patients.organization_id", "patients.id"]
        ),
        CheckConstraint(
            "consent_type IN ('data_processing','ai_assisted_documentation','contact_reminders')",
            name="type",
        ),
        CheckConstraint("status IN ('granted','withdrawn')", name="status"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class ConsentEvent(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "consent_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "consent_record_id"],
            ["consent_records.organization_id", "consent_records.id"],
        ),
        CheckConstraint("method IN ('verbal','written','digital')", name="method"),
    )
    consent_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
