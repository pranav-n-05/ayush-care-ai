import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import APIModel


class EncounterCreate(APIModel):
    visit_reason: str | None = Field(None, max_length=200)
    clinic_id: uuid.UUID | None = None


class EncounterStatusUpdate(APIModel):
    status: Literal["open", "in_review", "closed"]


class EncounterOut(APIModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    clinic_id: uuid.UUID | None
    status: str
    visit_reason: str | None
    started_at: datetime
    closed_at: datetime | None
