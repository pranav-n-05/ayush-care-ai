import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import ERROR_RESPONSES, APIModel
from app.db.session import get_db
from app.modules.followups import service
from app.modules.identity.access import OrgContext, require
from app.modules.identity.permissions import P

router = APIRouter(prefix="/api/v1", tags=["follow-ups"], responses=ERROR_RESPONSES)


class TaskIn(APIModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    due_at: datetime
    channel: Literal["sms", "email", "phone_call"]


class TaskOut(APIModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    due_at: datetime
    channel: str
    purpose_code: str
    status: str


class TaskStatusIn(APIModel):
    status: Literal["completed", "cancelled"]


class NotificationOut(APIModel):
    id: uuid.UUID
    channel: str
    template_code: str
    status: str
    attempts: int
    provider: str | None
    sent_at: datetime | None
    created_at: datetime


@router.post("/follow-ups", response_model=TaskOut, status_code=201)
async def create(
    body: TaskIn,
    ctx: OrgContext = Depends(require(P.FOLLOWUP_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    return TaskOut.model_validate(
        await service.create_task(
            db, ctx, body.patient_id, body.encounter_id, body.due_at, body.channel
        )
    )


@router.get("/follow-ups", response_model=list[TaskOut])
async def list_tasks(
    patient_id: uuid.UUID | None = None,
    status: Literal["scheduled", "completed", "cancelled"] | None = Query(None),
    ctx: OrgContext = Depends(require(P.FOLLOWUP_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    return [
        TaskOut.model_validate(t)
        for t in await service.list_tasks(db, ctx.organization_id, patient_id, status)
    ]


@router.put("/follow-ups/{task_id}/status", response_model=TaskOut)
async def set_status(
    task_id: uuid.UUID,
    body: TaskStatusIn,
    ctx: OrgContext = Depends(require(P.FOLLOWUP_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    return TaskOut.model_validate(await service.set_task_status(db, ctx, task_id, body.status))


@router.get("/follow-ups/{task_id}/notifications", response_model=list[NotificationOut])
async def notifications(
    task_id: uuid.UUID,
    ctx: OrgContext = Depends(require(P.FOLLOWUP_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    return [
        NotificationOut.model_validate(n)
        for n in await service.notifications_for(db, ctx.organization_id, task_id)
    ]
