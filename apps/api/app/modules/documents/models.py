import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, TenantOwned, Timestamps, UUIDPk

DOCUMENT_TYPES = ("prescription", "lab_report", "prior_note", "discharge_summary", "other")


class Document(UUIDPk, TenantOwned, Timestamps, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "encounter_id"], ["encounters.organization_id", "encounters.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "patient_id"], ["patients.organization_id", "patients.id"]
        ),
        CheckConstraint(
            "document_type IN ('prescription','lab_report','prior_note','discharge_summary','other')",
            name="type",
        ),
        CheckConstraint("status IN ('quarantined','available','rejected')", name="status"),
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="quarantined")
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DocumentVersion(UUIDPk, TenantOwned, CreatedAt, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("document_id", "version_number"),
        ForeignKeyConstraint(
            ["organization_id", "document_id"], ["documents.organization_id", "documents.id"]
        ),
        CheckConstraint(
            "scan_status IN ('pending','passed_validation_only','rejected')", name="scan_status"
        ),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Opaque key inside the storage backend. Never returned by the API.
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    display_filename: Mapped[str] = mapped_column(String(120), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
