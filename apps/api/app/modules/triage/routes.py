import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES, APIModel
from app.db.session import get_db
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P
from app.modules.triage import service

router = APIRouter(prefix="/api/v1", tags=["triage"], responses=ERROR_RESPONSES)


class TriageEventOut(APIModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    rule_version_id: uuid.UUID
    intake_answer_id: uuid.UUID
    answer_revision: int
    severity: str
    reason: str
    is_demo_rule: bool
    status: str
    evaluated_at: datetime
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    resolved_at: datetime | None
    resolution_code: str | None


class TransitionIn(APIModel):
    action: Literal["acknowledge", "escalate", "resolve"]
    resolution_code: str | None = None


class RuleOut(APIModel):
    rule_id: uuid.UUID
    code: str
    name: str
    version_id: uuid.UUID
    version_number: int
    status: str
    clinical_use_enabled: bool
    severity: str
    condition: dict[str, Any]


@router.get("/triage/events", response_model=list[TriageEventOut])
async def events(
    encounter_id: uuid.UUID | None = None,
    status: Literal["open", "acknowledged", "escalated", "resolved"] | None = Query(None),
    ctx: OrgContext = Depends(require(P.TRIAGE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TriageEventOut]:
    rows = await service.list_events(
        db, ctx.organization_id, encounter_id=encounter_id, status=status
    )
    return [TriageEventOut.model_validate(r) for r in rows]


@router.post("/triage/events/{event_id}/transition", response_model=TriageEventOut)
async def transition(
    event_id: uuid.UUID,
    body: TransitionIn,
    ctx: OrgContext = Depends(require(P.TRIAGE_ACKNOWLEDGE)),
    db: AsyncSession = Depends(get_db),
) -> TriageEventOut:
    return TriageEventOut.model_validate(
        await service.transition_event(db, ctx, event_id, body.action, body.resolution_code)
    )


@router.get("/triage/rules", response_model=list[RuleOut])
async def rules(
    ctx: OrgContext = Depends(require(P.TRIAGE_READ)), db: AsyncSession = Depends(get_db)
) -> list[RuleOut]:
    return [
        RuleOut(
            rule_id=r.id,
            code=r.code,
            name=r.name,
            version_id=v.id,
            version_number=v.version_number,
            status=v.status,
            clinical_use_enabled=v.clinical_use_enabled,
            severity=v.severity,
            condition=v.condition,
        )
        for r, v in await service.list_rules(db, ctx.organization_id)
    ]
