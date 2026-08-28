"""FastAPI entrypoint for Cloud Run / local uvicorn."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stillopen_core.config import get_settings
from stillopen_core.memory.fakes import init_bank
from stillopen_core.observability.logger import get_logger
from stillopen_core.observability.tracing import setup_tracing
from stillopen_core.security.secrets import hydrate_secrets

from stillopen_api.routes import (
    agents,
    audit,
    auth,
    filings,
    finish,
    health,
    jobs,
    memory,
    plans,
    tasks,
)

_logger = get_logger(__name__)


def create_app() -> FastAPI:
    hydrate_secrets()
    get_settings.cache_clear()
    settings = get_settings()
    setup_tracing()
    init_bank()
    app = FastAPI(
        title="Still Open API",
        version="0.1.0",
        description="Name the open task. Ask if it is done. Close that pile.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ],
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Stillopen-Job-Token",
            "X-Stillopen-User-Token",
        ],
    )
    app.include_router(health.router)
    app.include_router(plans.router)
    app.include_router(memory.router)
    app.include_router(jobs.router)
    app.include_router(tasks.router)
    app.include_router(finish.router)
    app.include_router(audit.router)
    app.include_router(agents.router)
    app.include_router(filings.router)
    app.include_router(auth.router)
    _logger.info(
        "api.ready",
        env=settings.env.value,
        gemini=(
            "vertex"
            if settings.use_vertex and settings.gcp_project
            else "key"
            if settings.has_gemini
            else "off"
        ),
        otel=settings.otel_exporter.value,
        armor=settings.armor_backend,
    )
    return app


app = create_app()
