import asyncio
import uuid
from datetime import timedelta

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import update

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.ocr.models import OCRJob
from app.workers.dispatch import InProcessDispatcher, recover_jobs, set_dispatcher
from tests.factories import create_encounter, create_patient, make_org
from tests.test_documents_ocr import SYNTHETIC_RX


@pytest.mark.parametrize(
    "url", ["postgres://u:p@h:5432/d", "postgresql://u:p@h/d", "postgresql+asyncpg://u:p@h/d"]
)
def test_provider_database_urls_use_asyncpg(url):
    s = Settings(database_url=url)
    assert s.database_url.get_secret_value().startswith("postgresql+asyncpg://u:p@h")


def test_production_rejects_inline_dispatcher_but_allows_inprocess():
    prod = {
        "environment": "production",
        "database_url": SecretStr("postgresql://u:p@h/d"),
        "cookie_secure": True,
    }
    with pytest.raises(ValidationError):
        Settings(**prod, job_dispatcher="inline")
    assert Settings(**prod, job_dispatcher="inprocess").job_dispatcher == "inprocess"


async def _queued_ocr_job(login_as):
    org = await make_org()
    c = await login_as(org.users["clinical_assistant"])
    enc = await create_encounter(c, (await create_patient(c))["id"])
    doc = (
        await c.post(
            f"/api/v1/encounters/{enc['id']}/documents",
            files={"file": ("rx.txt", SYNTHETIC_RX)},
            data={"document_type": "prescription"},
        )
    ).json()
    return c, doc


async def test_inprocess_dispatcher_runs_job_after_request(login_as):
    c, doc = await _queued_ocr_job(login_as)
    d = InProcessDispatcher()
    set_dispatcher(d)
    try:
        job = (
            await c.post(
                f"/api/v1/documents/{doc['id']}/process", headers={"Idempotency-Key": "inproc-0001"}
            )
        ).json()
        assert job["status"] == "queued"
        await d.drain()
    finally:
        set_dispatcher(None)
    assert (await c.get(f"/api/v1/ocr-jobs/{job['id']}")).json()["status"] == "succeeded"


async def test_recover_jobs_redispatches_queued_and_orphaned(login_as, dispatcher):
    c, doc = await _queued_ocr_job(login_as)
    job = (
        await c.post(
            f"/api/v1/documents/{doc['id']}/process", headers={"Idempotency-Key": "inproc-0002"}
        )
    ).json()
    dispatcher.enqueued.clear()
    assert await recover_jobs() == 1
    async with session_scope() as db:
        await db.execute(
            update(OCRJob).values(status="running", started_at=utcnow() - timedelta(minutes=30))
        )
    assert await recover_jobs() == 1
    assert dispatcher.enqueued == [("ocr", uuid.UUID(job["id"]))] * 2
    await asyncio.sleep(0)


async def test_missing_stored_file_is_409_not_500(login_as):
    from app.modules.documents.storage import get_storage

    c, doc = await _queued_ocr_job(login_as)
    from sqlalchemy import select

    from app.modules.documents.models import DocumentVersion

    async with session_scope() as db:
        key = await db.scalar(select(DocumentVersion.storage_key))
    get_storage().delete(key)
    r = await c.get(f"/api/v1/documents/{doc['id']}/content")
    assert r.status_code == 409 and r.json()["error"]["code"] == "file_unavailable"


@pytest.mark.parametrize(
    "kind,cls",
    [
        ("inline", "InlineRecorder"),
        ("inprocess", "InProcessDispatcher"),
        ("celery", "CeleryDispatcher"),
    ],
)
def test_dispatcher_selected_from_settings(monkeypatch, kind, cls):
    from app.core.config import get_settings
    from app.workers import dispatch

    monkeypatch.setattr(get_settings(), "job_dispatcher", kind)
    dispatch.set_dispatcher(None)
    try:
        assert type(dispatch.get_dispatcher()).__name__ == cls
    finally:
        dispatch.set_dispatcher(None)


async def test_ocr_missing_file_fails_without_retry(login_as):
    from sqlalchemy import select

    from app.modules.documents.models import DocumentVersion
    from app.modules.documents.storage import get_storage
    from app.modules.ocr.service import run_ocr_job

    c, doc = await _queued_ocr_job(login_as)
    job = (
        await c.post(
            f"/api/v1/documents/{doc['id']}/process", headers={"Idempotency-Key": "inproc-0003"}
        )
    ).json()
    async with session_scope() as db:
        get_storage().delete(await db.scalar(select(DocumentVersion.storage_key)))
    assert await run_ocr_job(uuid.UUID(job["id"])) == "failed"
    j = (await c.get(f"/api/v1/ocr-jobs/{job['id']}")).json()
    assert j["attempts"] == 1 and "upload it again" in j["failure_reason"]
