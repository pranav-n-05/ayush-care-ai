import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.audit.service import add_audit
from app.modules.documents.models import Document, DocumentVersion
from app.modules.documents.service import get_version
from app.modules.documents.storage import get_storage
from app.modules.identity.access import OrgContext
from app.modules.ocr.extraction import extract_entities
from app.modules.ocr.models import ExtractedEntity, OCRJob
from app.providers.ocr import OCRTransientError, OCRUnsupported, get_ocr_provider

log = get_logger("ocr")
RUNNING_TIMEOUT = timedelta(minutes=10)  # a crashed worker leaves "running"; reclaim after this


async def request_processing(
    db: AsyncSession, ctx: OrgContext, document_id: uuid.UUID, idempotency_key: str
) -> tuple[OCRJob, bool]:
    """Returns (job, created). Same key for the same document version returns the same job."""
    if not 8 <= len(idempotency_key) <= 100:
        raise ValidationFailed("Idempotency-Key header must be 8-100 characters")
    version = await get_version(db, ctx.organization_id, document_id)
    doc = await db.get(Document, document_id)
    assert doc is not None
    if doc.status != "available":
        raise Conflict("Document is not available for processing")
    existing = await db.scalar(
        select(OCRJob).where(
            OCRJob.organization_id == ctx.organization_id,
            OCRJob.document_version_id == version.id,
            OCRJob.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing, False
    job = OCRJob(
        organization_id=ctx.organization_id,
        document_version_id=version.id,
        idempotency_key=idempotency_key,
        requested_by_user_id=ctx.user_id,
    )
    db.add(job)
    await db.flush()
    add_audit(
        db,
        action="ocr.requested",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="ocr_job",
        entity_id=job.id,
    )
    await db.commit()
    return job, True


async def get_job(db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID) -> OCRJob:
    job = await db.scalar(
        select(OCRJob).where(OCRJob.id == job_id, OCRJob.organization_id == org_id)
    )
    if job is None:
        raise NotFound("Job not found")
    return job


async def run_ocr_job(job_id: uuid.UUID) -> str:
    """Worker entry point. Creates its own sessions; retrieves everything by ID server-side.
    Returns the resulting status. Safe to call repeatedly (idempotent)."""
    async with session_scope() as db:
        job = await db.scalar(
            select(OCRJob).where(OCRJob.id == job_id).with_for_update(skip_locked=True)
        )
        if job is None:
            return "missing"
        stuck = (
            job.status == "running"
            and job.started_at is not None
            and utcnow() - job.started_at > RUNNING_TIMEOUT
        )
        if job.status in ("succeeded", "failed") or (job.status == "running" and not stuck):
            return job.status
        if job.attempts >= job.max_attempts:
            job.status, job.failure_reason = "failed", "Retry limit reached"
            return job.status
        job.status, job.attempts, job.started_at = "running", job.attempts + 1, utcnow()
        version = await db.get(DocumentVersion, job.document_version_id)
        assert version is not None and version.organization_id == job.organization_id
        storage_key, mime = version.storage_key, version.mime_type
        org_id = job.organization_id

    provider = get_ocr_provider()
    status, reason, result = "succeeded", None, None
    try:
        data = get_storage().get(storage_key)
        result = provider.extract(data, mime)
    except OCRUnsupported as exc:
        status, reason = "failed", str(exc)[:200]
    except FileNotFoundError:
        status, reason = "failed", "Stored file is no longer available; upload it again"
    except (OCRTransientError, TimeoutError, OSError) as exc:
        status, reason = "retry", "Temporary OCR failure"
        log.warning("ocr_transient_failure", job_id=str(job_id), error=type(exc).__name__)

    async with session_scope() as db:
        job = await db.scalar(select(OCRJob).where(OCRJob.id == job_id).with_for_update())
        assert job is not None
        job.provider, job.provider_version = provider.name, provider.version
        job.finished_at = utcnow()
        if status == "retry":
            job.status = "queued" if job.attempts < job.max_attempts else "failed"
            job.failure_reason = reason if job.status == "failed" else None
        elif status == "failed":
            job.status, job.failure_reason = "failed", reason
        else:
            assert result is not None
            job.status, job.result_text = "succeeded", result.text
            for c in extract_entities(result):
                db.add(
                    ExtractedEntity(
                        organization_id=org_id,
                        ocr_job_id=job.id,
                        document_version_id=job.document_version_id,
                        lineage_id=uuid.uuid4(),
                        revision=1,
                        is_current=True,
                        entity_type=c.entity_type,
                        text=c.text,
                        attributes=c.attributes,
                        page=c.page,
                        line=c.line,
                        region=c.region,
                        confidence=c.confidence,
                        verification_status="unverified",
                    )
                )
        add_audit(
            db,
            action="ocr.job_finished",
            organization_id=org_id,
            actor_user_id=None,
            entity_type="ocr_job",
            entity_id=job.id,
            outcome="success" if job.status == "succeeded" else "failure",
            details={"status": job.status, "attempt": job.attempts},
        )
        return job.status


async def stale_queued_jobs(older_than: timedelta = timedelta(minutes=5)) -> list[uuid.UUID]:
    async with session_scope() as db:
        rows = await db.scalars(
            select(OCRJob.id)
            .where(OCRJob.status == "queued", OCRJob.updated_at < utcnow() - older_than)
            .limit(100)
        )
        return list(rows.all())


async def list_entities(
    db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID
) -> list[ExtractedEntity]:
    version = await get_version(db, org_id, document_id)
    return list(
        (
            await db.scalars(
                select(ExtractedEntity)
                .where(
                    ExtractedEntity.organization_id == org_id,
                    ExtractedEntity.document_version_id == version.id,
                    ExtractedEntity.is_current,
                )
                .order_by(ExtractedEntity.page, ExtractedEntity.line)
            )
        ).all()
    )


async def review_entity(
    db: AsyncSession,
    ctx: OrgContext,
    entity_id: uuid.UUID,
    action: str,
    expected_revision: int,
    corrected_text: str | None,
) -> ExtractedEntity:
    """Every review appends a new revision; the original extraction is preserved."""
    ent = await db.scalar(
        select(ExtractedEntity)
        .where(
            ExtractedEntity.id == entity_id, ExtractedEntity.organization_id == ctx.organization_id
        )
        .with_for_update()
    )
    if ent is None:
        raise NotFound("Extracted entity not found")
    if not ent.is_current or ent.revision != expected_revision:
        raise Conflict("Entity was reviewed by someone else; reload", code="stale_version")
    status = {"verify": "verified", "reject": "rejected", "correct": "corrected"}[action]
    if action == "correct" and not (corrected_text and corrected_text.strip()):
        raise ValidationFailed("corrected_text is required for corrections")
    if action != "correct" and corrected_text is not None:
        raise ValidationFailed("corrected_text is only allowed for corrections")
    ent.is_current = False
    await db.flush()
    new = ExtractedEntity(
        organization_id=ent.organization_id,
        ocr_job_id=ent.ocr_job_id,
        document_version_id=ent.document_version_id,
        lineage_id=ent.lineage_id,
        revision=ent.revision + 1,
        is_current=True,
        entity_type=ent.entity_type,
        text=corrected_text.strip() if action == "correct" and corrected_text else ent.text,
        attributes=ent.attributes,
        page=ent.page,
        line=ent.line,
        region=ent.region,
        confidence=ent.confidence,
        verification_status=status,
        reviewed_by_user_id=ctx.user_id,
        reviewed_at=utcnow(),
    )
    db.add(new)
    await db.flush()
    add_audit(
        db,
        action=f"ocr.entity_{status}",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="extracted_entity",
        entity_id=new.id,
        details={"revision": new.revision},
    )
    await db.commit()
    return new
