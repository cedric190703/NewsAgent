from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import LLMProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider

log = get_logger(__name__)


@lru_cache
def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "mock":
        log.info("using mock LLM provider")
        return MockProvider()
    log.info(
        "using ollama LLM provider",
        extra={"model": settings.ollama_model, "base_url": settings.ollama_base_url},
    )
    return OllamaProvider(settings)


async def close_llm_provider() -> None:
    provider = get_llm_provider()
    closer = getattr(provider, "aclose", None)
    if closer is not None:
        await closer()
