"""FastAPI application wiring: lifespan, middleware, routers, error handling."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.news import router as news_router
from app.api.runs import router as runs_router
from app.core.config import settings
from app.core.http import close_client
from app.core.logging import configure_logging, get_logger
from app.providers.factory import close_llm_provider
from app.services import store
from app.services.scheduler import get_scheduler

configure_logging(settings.log_level, settings.json_logs)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_db()

    stale = await store.mark_stale_runs_cancelled()
    if stale:
        log.info("retired interrupted runs", extra={"count": stale})
    pruned = await store.prune_runs()
    if pruned:
        log.info("pruned old runs", extra={"count": pruned})

    scheduler = get_scheduler()
    if settings.enable_scheduler:
        scheduler.start()

    log.info(
        "startup complete",
        extra={"version": settings.app_version, "environment": settings.environment},
    )
    try:
        yield
    finally:
        await scheduler.stop()
        await close_llm_provider()
        await close_client()
        await store.close_db()
        log.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Multi-agent news intelligence API powered by LangGraph.\n\n"
        "- `POST /api/runs` + `GET /api/runs/{id}/stream` — run with live progress.\n"
        "- `POST /api/news/query` — one structured briefing, synchronously.\n"
        "- `POST /api/schedules` — recurring newsletters on a cron expression."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tag every request with an id and log how long it took."""

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        log.exception(
            "request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    # SSE streams stay open for the whole run; their duration is meaningless.
    if not request.url.path.endswith("/stream"):
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            },
        )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422s are the most common integration mistake; say exactly which field."""

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "errors": [
                {
                    "field": ".".join(str(part) for part in error["loc"][1:]) or "body",
                    "message": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(news_router, prefix="/api/news", tags=["news"])
app.include_router(runs_router, prefix="/api", tags=["runs"])
