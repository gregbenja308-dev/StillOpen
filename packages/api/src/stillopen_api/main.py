"""FastAPI entrypoint for Cloud Run / local uvicorn."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stillopen_core.config import get_settings
from stillopen_core.memory.fakes import init_bank
from stillopen_core.observability.logger import get_logger

from stillopen_api.routes import auth, health, jobs, memory, plans, tasks

_logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
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
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(plans.router)
    app.include_router(memory.router)
    app.include_router(auth.router)
    app.include_router(jobs.router)
    app.include_router(tasks.router)
    _logger.info("api.ready", env=settings.env.value)
    return app


app = create_app()
