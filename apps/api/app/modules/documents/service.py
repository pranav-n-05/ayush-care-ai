import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.modules.audit.service import add_audit, record_audit_independently
from app.modules.documents.models import Document, DocumentVersion
from app.modules.documents.storage import get_storage, make_key
from app.modules.documents.validation import UploadRejected, validate_upload
from app.modules.encounters.service import get_encounter
from app.modules.identity.access import OrgContext


async def upload_document(
    db: AsyncSession,
    ctx: OrgContext,
    encounter_id: uuid.UUID,
    document_type: str,
    filename: str,
    data: bytes,
) -> tuple[Document, DocumentVersion]:
    enc = await get_encounter(db, ctx.organization_id, encounter_id)
    if enc.status == "closed":
        raise Conflict("Encounter is closed")
    s = get_settings()
    try:
        validated = validate_upload(
            filename, data, max_bytes=s.max_upload_bytes, max_pdf_pages=s.max_pdf_pages
        )
    except UploadRejected as exc:
        await record_audit_independently(
            action="document.upload_rejected",
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user_id,
            entity_type="encounter",
            entity_id=encounter_id,
            outcome="failure",
            details={"reason": str(exc)[:100]},
        )
        raise ValidationFailed(str(exc), code="upload_rejected") from exc

    doc = Document(
        organization_id=ctx.organization_id,
        encounter_id=enc.id,
        patient_id=enc.patient_id,
        document_type=document_type,
        status="quarantined",
    )
    db.add(doc)
    await db.flush()
    key = make_key(uuid.uuid4().hex)
    version = DocumentVersion(
        organization_id=ctx.organization_id,
        document_id=doc.id,
        version_number=1,
        storage_key=key,
        display_filename=validated.display_filename,
        mime_type=validated.mime_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=validated.page_count,
        scan_status="pending",
        uploaded_by_user_id=ctx.user_id,
    )
    db.add(version)
    await db.flush()
    get_storage().put(key, data)
    # No antivirus engine is configured: we release the file after structural validation only
    # and record that fact rather than claiming it was scanned.
    version.scan_status = "passed_validation_only"
    doc.status = "available"
    add_audit(
        db,
        action="document.uploaded",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="document",
        entity_id=doc.id,
        details={"mime": validated.mime_type, "bytes": len(data)},
    )
    try:
        await db.commit()
    except BaseException:
        get_storage().delete(key)
        raise
    return doc, version


async def get_document(db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = await db.scalar(
        select(Document).where(Document.id == document_id, Document.organization_id == org_id)
    )
    if doc is None:
        raise NotFound("Document not found")
    return doc


async def get_version(
    db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID, version_number: int | None = None
) -> DocumentVersion:
    doc = await get_document(db, org_id, document_id)
    v = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == org_id,
            DocumentVersion.version_number == (version_number or doc.current_version_number),
        )
    )
    if v is None:
        raise NotFound("Document version not found")
    return v


async def list_for_encounter(
    db: AsyncSession, org_id: uuid.UUID, encounter_id: uuid.UUID
) -> list[tuple[Document, DocumentVersion]]:
    await get_encounter(db, org_id, encounter_id)
    rows = await db.execute(
        select(Document, DocumentVersion)
        .join(
            DocumentVersion,
            (DocumentVersion.document_id == Document.id)
            & (DocumentVersion.version_number == Document.current_version_number),
        )
        .where(Document.organization_id == org_id, Document.encounter_id == encounter_id)
        .order_by(Document.created_at)
    )
    return [(d, v) for d, v in rows.all()]


async def read_content(
    db: AsyncSession, ctx: OrgContext, document_id: uuid.UUID, version_number: int | None
) -> tuple[DocumentVersion, bytes]:
    v = await get_version(db, ctx.organization_id, document_id, version_number)
    doc = await get_document(db, ctx.organization_id, document_id)
    if doc.status != "available":
        raise Conflict("Document is not available for download")
    data = get_storage().get(v.storage_key)
    if hashlib.sha256(data).hexdigest() != v.sha256:
        raise Conflict("Stored file failed its integrity check")
    add_audit(
        db,
        action="document.downloaded",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="document",
        entity_id=document_id,
        details={"version": v.version_number},
    )
    await db.commit()
    return v, data
