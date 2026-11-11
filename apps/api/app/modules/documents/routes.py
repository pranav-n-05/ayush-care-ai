import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.schemas import ERROR_RESPONSES, APIModel
from app.db.session import get_db
from app.modules.documents import service
from app.modules.documents.models import Document, DocumentVersion
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.ocr import service as ocr
from app.modules.ocr.models import ExtractedEntity, OCRJob
from app.workers.dispatch import get_dispatcher

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=ERROR_RESPONSES)


class DocumentOut(APIModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    document_type: str
    status: str
    version_number: int
    display_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    scan_status: str
    created_at: datetime


class OCRJobOut(APIModel):
    id: uuid.UUID
    document_version_id: uuid.UUID
    status: str
    attempts: int
    max_attempts: int
    provider: str | None
    provider_version: str | None
    failure_reason: str | None
    created_at: datetime
    finished_at: datetime | None


class OCRJobDetail(OCRJobOut):
    result_text: str | None


class EntityOut(APIModel):
    id: uuid.UUID
    lineage_id: uuid.UUID
    revision: int
    entity_type: str
    text: str
    attributes: dict[str, object]
    page: int | None
    line: int | None
    confidence: float | None
    verification_status: str
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None


class EntityReview(APIModel):
    action: Literal["verify", "reject", "correct"]
    expected_revision: int
    corrected_text: str | None = None


def _doc_out(d: Document, v: DocumentVersion) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        encounter_id=d.encounter_id,
        document_type=d.document_type,
        status=d.status,
        version_number=v.version_number,
        display_filename=v.display_filename,
        mime_type=v.mime_type,
        size_bytes=v.size_bytes,
        sha256=v.sha256,
        page_count=v.page_count,
        scan_status=v.scan_status,
        created_at=d.created_at,
    )


@router.post("/encounters/{encounter_id}/documents", response_model=DocumentOut, status_code=201)
async def upload(
    encounter_id: uuid.UUID,
    file: UploadFile = File(...),
    document_type: Literal[
        "prescription", "lab_report", "prior_note", "discharge_summary", "other"
    ] = Form(...),
    ctx: OrgContext = Depends(require(P.DOCUMENT_UPLOAD)),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # bounded read
    if len(data) > limit:
        raise ValidationFailed("File exceeds the upload size limit", code="upload_rejected")
    d, v = await service.upload_document(
        db, ctx, encounter_id, document_type, file.filename or "document", data
    )
    return _doc_out(d, v)


@router.get("/encounters/{encounter_id}/documents", response_model=list[DocumentOut])
async def list_docs(
    encounter_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    return [
        _doc_out(d, v)
        for d, v in await service.list_for_encounter(db, ctx.organization_id, encounter_id)
    ]


@router.get("/documents/{document_id}/content")
async def download(
    document_id: uuid.UUID,
    version: int | None = None,
    ctx: OrgContext = Depends(require(P.DOCUMENT_DOWNLOAD)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    v, data = await service.read_content(db, ctx, document_id, version)
    return Response(
        content=data,
        media_type=v.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{v.display_filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/documents/{document_id}/process", response_model=OCRJobOut, status_code=202)
async def process(
    document_id: uuid.UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ctx: OrgContext = Depends(require(P.OCR_PROCESS)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    job, created = await ocr.request_processing(db, ctx, document_id, idempotency_key)
    if created:
        get_dispatcher().enqueue("ocr", job.id)  # after commit
    body = OCRJobOut.model_validate(job).model_dump(mode="json")
    return JSONResponse(status_code=202 if created else 200, content=body)


@router.get("/ocr-jobs/{job_id}", response_model=OCRJobDetail)
async def job_status(
    job_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OCRJob:
    return await ocr.get_job(db, ctx.organization_id, job_id)


@router.get("/documents/{document_id}/entities", response_model=list[EntityOut])
async def entities(
    document_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ExtractedEntity]:
    return await ocr.list_entities(db, ctx.organization_id, document_id)


@router.post("/extracted-entities/{entity_id}/review", response_model=EntityOut)
async def review(
    entity_id: uuid.UUID,
    body: EntityReview,
    ctx: OrgContext = Depends(require(P.OCR_VERIFY)),
    db: AsyncSession = Depends(get_db),
) -> ExtractedEntity:
    return await ocr.review_entity(
        db, ctx, entity_id, body.action, body.expected_revision, body.corrected_text
    )
