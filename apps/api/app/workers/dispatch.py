"""Job dispatch. Jobs are persisted as rows first; dispatch happens only AFTER the creating
transaction commits, and messages carry only (kind, job_id). If publishing fails, the row
stays 'queued' and the periodic sweeper re-publishes it (the jobs table acts as the outbox)."""

import uuid
from typing import Literal, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

JobKind = Literal["ocr", "summary"]
log = get_logger("dispatch")


class Dispatcher(Protocol):
    def enqueue(self, kind: JobKind, job_id: uuid.UUID) -> None: ...


class InlineRecorder:
    """Records enqueued jobs without executing them (tests/dev without a broker). Tests run the
    worker functions explicitly, so nothing silently 'completes'."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[JobKind, uuid.UUID]] = []

    def enqueue(self, kind: JobKind, job_id: uuid.UUID) -> None:
        self.enqueued.append((kind, job_id))


class CeleryDispatcher:
    def enqueue(self, kind: JobKind, job_id: uuid.UUID) -> None:
        from app.workers.celery_app import celery_app

        try:
            celery_app.send_task(f"ayushcare.{kind}", args=[str(job_id)])
        except Exception as exc:  # noqa: BLE001 - broker outage must not fail the request
            log.warning("dispatch_failed", kind=kind, job_id=str(job_id), error=type(exc).__name__)


_dispatcher: Dispatcher | None = None


def get_dispatcher() -> Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = (
            CeleryDispatcher() if get_settings().job_dispatcher == "celery" else InlineRecorder()
        )
    return _dispatcher


def set_dispatcher(d: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = d
