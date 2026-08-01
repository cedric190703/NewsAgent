from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI News Agent"
    environment: Literal["local", "test", "production"] = "local"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    llm_provider: Literal["ollama", "mock"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral:latest"
    llm_timeout_seconds: int = 60
    llm_max_concurrency: int = 4

    # --- search providers ---
    # "auto" resolves to every provider that has credentials, else the mock.
    search_providers: list[str] = Field(default_factory=lambda: ["auto"])
    tavily_api_key: str | None = None
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    newsapi_key: str | None = None
    newsapi_language: str = "en"
    rss_feeds: list[str] = Field(
        default_factory=lambda: [
            "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://www.theverge.com/rss/index.xml",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.wired.com/feed/rss",
            "https://feeds.nature.com/nature/rss/current",
            "https://science.sciencemag.org/rss/current.xml",
            "https://www.theguardian.com/world/rss",
        ]
    )

    # --- fetching / extraction ---
    source_fetch_timeout_seconds: int = 15
    http_user_agent: str = "NewsAgent/0.2 (+https://example.local)"
    enable_article_extraction: bool = True
    min_content_chars: int = 400
    max_article_chars: int = 16000

    # --- graph behaviour ---
    results_per_subtopic: int = 8
    min_relevant_results: int = 4
    max_search_attempts: int = 2
    relevance_threshold: float = 0.35
    enable_factcheck: bool = True

    # --- storage ---
    data_dir: str = "./data"
    checkpoint_db: str = "./data/checkpoints.sqlite"
    runs_db: str = "./data/runs.sqlite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
