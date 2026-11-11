"""Test harness: real PostgreSQL (docker compose `db`), schema built by Alembic migrations.
Synthetic data only."""

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

ADMIN_DSN = os.environ.get(
    "AYUSH_TEST_ADMIN_DSN", "postgresql://ayushcare:ayushcare_dev_only@localhost:5432/postgres"
)
TEST_DB = os.environ.get("AYUSH_TEST_DB", "ayushcare_test")
TEST_URL = (
    ADMIN_DSN.rsplit("/", 1)[0].replace("postgresql://", "postgresql+asyncpg://") + f"/{TEST_DB}"
)

os.environ.update(
    {
        "AYUSH_ENVIRONMENT": "test",
        "AYUSH_DATABASE_URL": TEST_URL,
        "AYUSH_COOKIE_SECURE": "false",
        "AYUSH_TRUSTED_ORIGINS": '["http://test", "http://localhost:3000"]',
        "AYUSH_JOB_DISPATCHER": "inline",
        "AYUSH_STORAGE_ROOT": tempfile.mkdtemp(prefix="ayush-test-storage-"),
    }
)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.session import dispose_engine, session_scope  # noqa: E402
from app.main import create_app  # noqa: E402
from app.workers.dispatch import InlineRecorder, set_dispatcher  # noqa: E402

KEEP_TABLES = {"roles", "permissions", "role_permissions", "alembic_version"}
PASSWORD = "Synthetic-Test-Password-1"


async def _recreate_db(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.attributes["database_url"] = url
    return cfg


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    await _recreate_db(TEST_DB)
    await asyncio.to_thread(command.upgrade, alembic_config(TEST_URL), "head")
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def clean_tables(database: None) -> AsyncIterator[None]:
    yield
    async with session_scope() as db:
        rows = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = [r[0] for r in rows if r[0] not in KEEP_TABLES]
        await db.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))


@pytest.fixture
def dispatcher() -> InlineRecorder:
    rec = InlineRecorder()
    set_dispatcher(rec)
    return rec


@pytest.fixture
def app(dispatcher: InlineRecorder):  # type: ignore[no-untyped-def]
    return create_app()


ClientFactory = Callable[..., Awaitable[AsyncClient]]


@pytest.fixture
async def anon(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def login_as(app) -> AsyncIterator[ClientFactory]:  # type: ignore[no-untyped-def]
    clients: list[AsyncClient] = []

    async def _login(email: str, password: str = PASSWORD) -> AsyncClient:
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        r = await c.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        return c

    yield _login
    for c in clients:
        await c.aclose()


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
