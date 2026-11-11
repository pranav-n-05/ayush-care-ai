import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, model_validator

from app.core.schemas import APIModel

Sex = Literal["female", "male", "intersex", "unknown"]
Lang = Literal["en", "hi", "ta"]
ConsentType = Literal["data_processing", "ai_assisted_documentation", "contact_reminders"]
PHONE = r"^\+?[0-9]{7,15}$"


class PatientBase(APIModel):
    given_name: str = Field(min_length=1, max_length=100)
    family_name: str = Field("", max_length=100)
    birth_date: date | None = None
    birth_date_precision: Literal["exact", "year", "estimated_from_age"] = "exact"
    age_years: int | None = Field(None, ge=0, le=130)
    age_recorded_on: date | None = None
    sex_for_clinical_use: Sex
    phone: str | None = Field(None, pattern=PHONE)
    email: EmailStr | None = None
    address_line: str | None = Field(None, max_length=300)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, pattern=r"^[0-9A-Za-z \-]{3,12}$")
    preferred_language: Lang = "en"
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, pattern=PHONE)
    emergency_contact_relation: str | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def _age(self) -> "PatientBase":
        if self.birth_date is None:
            if self.age_years is None or self.age_recorded_on is None:
                raise ValueError("Provide birth_date, or age_years with age_recorded_on")
            self.birth_date_precision = "estimated_from_age"
        elif self.birth_date > date.today():
            raise ValueError("birth_date cannot be in the future")
        if self.age_recorded_on and self.age_recorded_on > date.today():
            raise ValueError("age_recorded_on cannot be in the future")
        return self


class ConsentInput(APIModel):
    consent_type: ConsentType
    status: Literal["granted", "withdrawn"]
    method: Literal["verbal", "written", "digital"]


class PatientCreate(PatientBase):
    consents: list[ConsentInput] = Field(default_factory=list)


class PatientUpdate(PatientBase):
    lock_version: int = Field(description="Version you are editing; stale versions get 409")


class DuplicateCandidate(APIModel):
    id: uuid.UUID
    record_number: str
    match_reasons: list[str]


class PatientOut(PatientBase):
    id: uuid.UUID
    record_number: str
    is_active: bool
    lock_version: int
    created_at: datetime


class PatientCreated(APIModel):
    patient: PatientOut
    possible_duplicates: list[DuplicateCandidate] = Field(
        description="Flags for human review only. Records are never merged automatically."
    )


class PatientListItem(APIModel):
    id: uuid.UUID
    record_number: str
    given_name: str
    family_name: str
    birth_date: date | None
    age_years: int | None
    sex_for_clinical_use: Sex
    preferred_language: Lang
    created_at: datetime


class ConsentOut(APIModel):
    consent_type: ConsentType
    status: str
    updated_at: datetime


class ConsentEventOut(APIModel):
    consent_type: str
    status: str
    method: str
    recorded_by_user_id: uuid.UUID
    created_at: datetime


class IdentifierIn(APIModel):
    system: str = Field(pattern=r"^[a-z0-9\-]{2,50}$")
    value: str = Field(min_length=1, max_length=100)


class IdentifierOut(IdentifierIn):
    id: uuid.UUID
