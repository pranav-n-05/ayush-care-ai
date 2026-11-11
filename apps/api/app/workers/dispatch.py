"""Job dispatch. Jobs are persisted as rows first; dispatch happens only AFTER the creating
transaction commits, and messages carry only (kind, job_id). If publishing fails, the row
stays 'queued' and the periodic sweeper re-publishes it (the jobs table acts as the outbox)."""

import asyncio
import uuid
from datetime import timedelta
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


class InProcessDispatcher:
    """Runs jobs as asyncio tasks in the API process, after the response is sent. Retries
    follow the job row's own bounded max_attempts. Suitable for a single small instance only:
    work in flight is lost if the process stops, and is picked up again by `recover_jobs()`
    on the next startup because job rows stay 'queued'."""

    RETRY_DELAY_SECONDS = 5.0

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def enqueue(self, kind: JobKind, job_id: uuid.UUID) -> None:
        task = asyncio.get_running_loop().create_task(self._run(kind, job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, kind: JobKind, job_id: uuid.UUID) -> None:
        from app.modules.ocr.service import run_ocr_job
        from app.modules.summaries.service import run_summary_job

        runner = run_ocr_job if kind == "ocr" else run_summary_job
        for _ in range(10):  # hard stop; the row's max_attempts is the real bound
            try:
                status = await runner(job_id)
            except Exception as exc:  # noqa: BLE001 - logged; row stays queued for recovery
                log.warning(
                    "inprocess_job_error", kind=kind, job_id=str(job_id), error=type(exc).__name__
                )
                return
            if status != "queued":
                return
            await asyncio.sleep(self.RETRY_DELAY_SECONDS)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


async def recover_jobs() -> int:
    """Re-dispatch jobs left 'queued' (e.g. the instance slept or restarted)."""
    from sqlalchemy import or_, select

    from app.core.timeutil import utcnow
    from app.db.session import session_scope
    from app.modules.ocr.models import OCRJob
    from app.modules.summaries.models import SummaryJob

    cutoff = utcnow() - timedelta(minutes=10)
    async with session_scope() as db:
        ocr_ids = (
            await db.scalars(
                select(OCRJob.id).where(
                    or_(
                        OCRJob.status == "queued",
                        (OCRJob.status == "running") & (OCRJob.started_at < cutoff),
                    )
                )
            )
        ).all()
        summary_ids = (
            await db.scalars(
                select(SummaryJob.id).where(
                    or_(
                        SummaryJob.status == "queued",
                        (SummaryJob.status == "running") & (SummaryJob.updated_at < cutoff),
                    )
                )
            )
        ).all()
    dispatcher = get_dispatcher()
    for jid in ocr_ids:
        dispatcher.enqueue("ocr", jid)
    for jid in summary_ids:
        dispatcher.enqueue("summary", jid)
    return len(ocr_ids) + len(summary_ids)


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
        kind = get_settings().job_dispatcher
        if kind == "celery":
            _dispatcher = CeleryDispatcher()
        elif kind == "inprocess":
            _dispatcher = InProcessDispatcher()
        else:
            _dispatcher = InlineRecorder()
    return _dispatcher


def set_dispatcher(d: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = d
