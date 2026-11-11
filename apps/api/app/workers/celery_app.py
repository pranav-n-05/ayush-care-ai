"""Celery worker. Messages carry job IDs only; tasks open their own DB sessions and load the
authorized, tenant-scoped records server-side. Delivery is at-least-once: task bodies are
idempotent and jobs are bounded by max_attempts stored on the row."""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine

settings = get_settings()
celery_app = Celery("ayushcare", broker=settings.redis_url.get_secret_value())
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "sweep-stale-jobs": {"task": "ayushcare.sweep", "schedule": 300.0},
        "dispatch-reminders": {"task": "ayushcare.reminders", "schedule": 600.0},
    },
)
configure_logging()


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    async def wrapper() -> T:
        try:
            return await coro
        finally:
            await dispose_engine()  # fresh engine per task loop; never shared across loops

    return asyncio.run(wrapper())


@celery_app.task(name="ayushcare.ocr", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def ocr_task(self: Any, job_id: str) -> str:
    from app.modules.ocr.service import run_ocr_job

    status = _run(run_ocr_job(uuid.UUID(job_id)))
    if status == "queued":
        raise self.retry(countdown=30 * (self.request.retries + 1))
    return status


@celery_app.task(name="ayushcare.summary", bind=True, max_retries=2)  # type: ignore[untyped-decorator]
def summary_task(self: Any, job_id: str) -> str:
    from app.modules.summaries.service import run_summary_job

    status = _run(run_summary_job(uuid.UUID(job_id)))
    if status == "queued":
        raise self.retry(countdown=20 * (self.request.retries + 1))
    return status


@celery_app.task(name="ayushcare.sweep")  # type: ignore[untyped-decorator]
def sweep_task() -> int:
    from app.modules.ocr.service import stale_queued_jobs

    ids = _run(stale_queued_jobs())
    for jid in ids:
        celery_app.send_task("ayushcare.ocr", args=[str(jid)])
    return len(ids)


@celery_app.task(name="ayushcare.reminders")  # type: ignore[untyped-decorator]
def reminders_task() -> dict[str, int]:
    from app.modules.followups.service import dispatch_due_reminders

    return _run(dispatch_due_reminders())
