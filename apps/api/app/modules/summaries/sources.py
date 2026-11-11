"""Collects the citable sources for one encounter in one tenant."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentVersion
from app.modules.intake.models import IntakeSession
from app.modules.ocr.models import ExtractedEntity


@dataclass(frozen=True)
class Source:
    kind: str
    id: str
    revision: int
    provenance: str
    label: str  # question code or entity type
    prompt_en: str  # English question text / entity type, for rendering
    section: str
    answer_status: str
    value: Any
    text_en: str | None  # English rendering if available (translation may be a draft)
    translation_status: str | None = None

    def ref(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "revision": self.revision}


@dataclass
class SourceSet:
    sources: list[Source]
    unanswered_required: list[tuple[str, str]]  # (question_code, state)

    def by_key(self) -> dict[tuple[str, str, int], Source]:
        return {(s.kind, s.id, s.revision): s for s in self.sources}

    def snapshot(self) -> list[dict[str, Any]]:
        return sorted((s.ref() for s in self.sources), key=lambda r: (r["kind"], r["id"]))

    def snapshot_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()


async def collect_sources(
    db: AsyncSession, org_id: uuid.UUID, encounter_id: uuid.UUID
) -> SourceSet:
    from app.modules.intake.service import load_session, question_states

    sources: list[Source] = []
    missing: list[tuple[str, str]] = []
    session_ids = (
        await db.scalars(
            select(IntakeSession.id).where(
                IntakeSession.organization_id == org_id,
                IntakeSession.encounter_id == encounter_id,
                IntakeSession.status.in_(("submitted", "reviewed")),
            )
        )
    ).all()
    for sid in session_ids:
        loaded = await load_session(db, org_id, sid)
        code_by_qid = {q.id: q for q in loaded.questions.values()}
        prompts = {q.code: q.text.en for _, q in loaded.definition.questions()}
        for qid, a in loaded.current.items():
            q = code_by_qid[qid]
            text_en = None
            if a.answer_status == "answered":
                if isinstance(a.value, str):
                    text_en = a.value if a.original_language == "en" else a.translated_text_en
                else:
                    text_en = json.dumps(a.value, ensure_ascii=False)
            sources.append(
                Source(
                    kind="intake_answer",
                    id=str(a.id),
                    revision=a.revision,
                    provenance=a.source,
                    label=q.code,
                    prompt_en=prompts[q.code],
                    section=q.section,
                    answer_status=a.answer_status,
                    value=a.value,
                    text_en=text_en,
                    translation_status=a.translation_status,
                )
            )
        for st in question_states(loaded):
            if st["state"] in ("unknown", "declined") or (
                st["required"] and st["state"] == "unanswered"
            ):
                missing.append((st["code"], st["state"]))

    rows = await db.execute(
        select(ExtractedEntity)
        .join(DocumentVersion, DocumentVersion.id == ExtractedEntity.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            ExtractedEntity.organization_id == org_id,
            Document.organization_id == org_id,
            Document.encounter_id == encounter_id,
            ExtractedEntity.is_current,
            # Only reviewer-verified/corrected OCR facts are citable.
            ExtractedEntity.verification_status.in_(("verified", "corrected")),
        )
    )
    for (e,) in rows.all():
        sources.append(
            Source(
                kind="extracted_entity",
                id=str(e.id),
                revision=e.revision,
                provenance="document_verified",
                label=e.entity_type,
                prompt_en=e.entity_type.replace("_", " "),
                section="document",
                answer_status="answered",
                value=e.text,
                text_en=e.text,
            )
        )
    return SourceSet(sources=sources, unanswered_required=missing)
