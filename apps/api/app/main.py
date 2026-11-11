import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.request_context import CorrelationIdMiddleware
from app.db.session import dispose_engine, get_engine
from app.modules.dashboard.routes import router as dashboard_router
from app.modules.documents.routes import router as documents_router
from app.modules.encounters.routes import router as encounters_router
from app.modules.followups.routes import router as followups_router
from app.modules.identity.routes import router as identity_router
from app.modules.intake.routes import router as intake_router
from app.modules.integrations.routes import router as integrations_router
from app.modules.patients.routes import router as patients_router
from app.modules.summaries.routes import router as summaries_router
from app.modules.triage.routes import router as triage_router

access_log = get_logger("access")

DESCRIPTION = """
AyushCare AI — practitioner-reviewed, multilingual case-taking API.

**Student portfolio project using synthetic data only. Not a medical device, not clinically
validated, not certified for ABDM or any regulation.** AI output is a draft until a
practitioner approves a specific version.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    @app.middleware("http")
    async def security_headers(request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        # Path only: query strings can contain search terms such as patient names.
        access_log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> JSONResponse:
        try:
            async with asyncio.timeout(settings.readiness_timeout_seconds):
                async with get_engine().connect() as conn:
                    await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - never leak connection details
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "checks": {"database": "fail"}}
            )
        return JSONResponse(status_code=200, content={"status": "ok", "checks": {"database": "ok"}})

    for r in (
        identity_router,
        patients_router,
        encounters_router,
        intake_router,
        triage_router,
        documents_router,
        summaries_router,
        followups_router,
        dashboard_router,
        integrations_router,
    ):
        app.include_router(r)
    return app


app = create_app()
