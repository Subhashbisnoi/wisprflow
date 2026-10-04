"""Application factory and process wiring."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.database import get_session_factory
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.security import PasswordHasher, TokenService
from app.features.audit.router import router as audit_router
from app.features.auth.router import router as auth_router
from app.features.dashboard.router import router as dashboard_router
from app.features.extraction.job import (
    EXTRACT_INVOICE_JOB,
    ExtractionJobHandler,
    recover_pending_jobs,
)
from app.features.extraction.providers.base import LLMProvider
from app.features.extraction.providers.fake_provider import FakeProvider
from app.features.extraction.providers.openai_provider import OpenAIProvider
from app.features.invoices.router import router as invoices_router
from app.features.review.router import router as review_router
from app.features.vendors.router import router as vendors_router
from app.infrastructure.jobs.in_process import InProcessJobQueue
from app.infrastructure.storage.local import LocalFileStorage

logger = logging.getLogger("app")


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    assert settings.openai_api_key is not None
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        text_model=settings.openai_text_model,
        vision_model=settings.openai_vision_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )


def build_container(settings: Settings) -> Container:
    return Container(
        settings=settings,
        session_factory=get_session_factory(),
        storage=LocalFileStorage(settings.storage_dir),
        job_queue=InProcessJobQueue(workers=settings.extraction_workers),
        llm_provider=build_llm_provider(settings),
        token_service=TokenService(settings),
        password_hasher=PasswordHasher(),
    )


def create_app(container: Container | None = None) -> FastAPI:
    settings = container.settings if container else get_settings()
    configure_logging(settings.log_level)
    container = container or build_container(settings)
    container.job_queue.register(EXTRACT_INVOICE_JOB, ExtractionJobHandler(container))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.start_job_queue:
            container.job_queue.start()
            recover_pending_jobs(container)
        logger.info(
            "ledgerline api started",
            extra={"env": settings.app_env, "llm_provider": container.llm_provider.name},
        )
        yield
        container.job_queue.stop()

    app = FastAPI(
        title="Ledgerline API",
        version="0.1.0",
        description="Accounts payable automation for Indian businesses.",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")

    @api.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        with container.session_factory() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    for router in (
        auth_router,
        invoices_router,
        review_router,
        audit_router,
        vendors_router,
        dashboard_router,
    ):
        api.include_router(router)
    app.include_router(api)
    return app
