"""Liveness, readiness, and a status summary the UI uses to warn about mock data."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas import HealthResponse, ReadinessResponse, StatusResponse
from app.core.config import settings
from app.providers.factory import get_llm_provider
from app.search.registry import available_provider_names, get_providers
from app.services import store
from app.services.scheduler import get_scheduler

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.app_version)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness() -> ReadinessResponse:
    """Reports dependency health without ever failing the request itself.

    Returning 200 with `status: degraded` is deliberate: the app stays usable
    with heuristic fallbacks when the LLM is down, so a hard failure here would
    take a working service out of a load balancer for no reason.
    """

    checks: dict[str, Any] = {}

    try:
        await store.list_runs(limit=1)
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    provider = get_llm_provider()
    health = getattr(provider, "health", None)
    if health is None:
        checks["llm"] = {"ok": True, "provider": settings.llm_provider}
    else:
        result = await health()
        checks["llm"] = {
            "ok": bool(result.get("reachable")),
            "provider": settings.llm_provider,
            **result,
        }

    checks["search"] = {"ok": True, "providers": list(available_provider_names())}
    checks["scheduler"] = {"ok": True, "running": get_scheduler().is_running}

    healthy = all(check.get("ok", False) for check in checks.values())
    return ReadinessResponse(status="ready" if healthy else "degraded", checks=checks)


@router.get("/status", response_model=StatusResponse, summary="Effective configuration")
async def status() -> StatusResponse:
    # What a default run will actually use, not merely what is available: with
    # SEARCH_PROVIDERS=mock the UI must not claim it is showing live data.
    providers = [provider.name for provider in get_providers()]
    return StatusResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        llm_model=(
            settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_provider
        ),
        search_providers=providers,
        using_real_data=any(name != "mock" for name in providers),
        rss_feeds_count=len(settings.rss_feeds or []),
        factcheck_enabled=settings.enable_factcheck,
        scheduler_running=get_scheduler().is_running,
    )
