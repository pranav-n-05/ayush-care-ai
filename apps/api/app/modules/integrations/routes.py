import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES
from app.db.session import get_db
from app.modules.audit.service import add_audit
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.integrations.fhir import patient_to_fhir
from app.modules.patients.service import get_patient

router = APIRouter(prefix="/api/v1", tags=["interoperability"], responses=ERROR_RESPONSES)


@router.get(
    "/patients/{patient_id}/fhir/Patient", summary="Export FHIR R4 Patient (unvalidated mapping)"
)
async def fhir_patient(
    patient_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.FHIR_EXPORT)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    p = await get_patient(db, ctx.organization_id, patient_id)
    add_audit(
        db,
        action="fhir.patient_exported",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="patient",
        entity_id=p.id,
    )
    await db.commit()
    return patient_to_fhir(p)
