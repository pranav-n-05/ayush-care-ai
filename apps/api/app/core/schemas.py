from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = Field(25, ge=1, le=100)
    offset: int = Field(0, ge=0, le=100_000)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Permission denied / CSRF failure"},
    404: {"model": ErrorResponse, "description": "Not found (or not visible to this tenant)"},
    409: {"model": ErrorResponse, "description": "Conflict / stale version"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
}
