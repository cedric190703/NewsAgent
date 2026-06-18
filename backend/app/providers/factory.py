from functools import lru_cache

from app.core.config import settings
from app.providers.base import LLMProvider
from app.providers.mock import MockProvider
from app.providers.ollama import OllamaProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    return OllamaProvider(settings)
