from fastapi import APIRouter

from app.core.config import settings
from app.search.registry import available_provider_names

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
async def status() -> dict[str, object]:
    providers = list(available_provider_names())
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_provider,
        "search_providers": providers,
        "using_real_data": any(p != "mock" for p in providers),
        "rss_feeds_count": len(settings.rss_feeds) if settings.rss_feeds else 0,
        "admin_enabled": True,
    }
