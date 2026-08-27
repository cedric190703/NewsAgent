import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# `NoDecode` stops pydantic-settings from JSON-parsing the raw env value, so the
# validator below can accept plain CSV (`A,B`) as well as a JSON array.
StrList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    app_name: str = "AI News Agent"
    app_version: str = "0.3.0"
    environment: Literal["local", "test", "production"] = "local"
    cors_origins: StrList = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- observability ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_logs: bool = False

    # --- LLM ---
    llm_provider: Literal["ollama", "mock"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral:latest"
    llm_timeout_seconds: int = 60
    llm_max_concurrency: int = 4
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # --- search providers ---
    # "auto" resolves to every provider that has credentials, else the mock.
    search_providers: StrList = Field(default_factory=lambda: ["auto"])
    tavily_api_key: str | None = None
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    newsapi_key: str | None = None
    newsapi_language: str = "en"
    rss_feeds: StrList = Field(
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
    http_user_agent: str = "NewsAgent/0.3 (+https://github.com/)"
    enable_article_extraction: bool = True
    min_content_chars: int = 400
    max_article_chars: int = 16000
    max_download_bytes: int = 5_000_000
    max_concurrent_fetches: int = 8
    feed_cache_ttl_seconds: int = 300
    article_cache_ttl_seconds: int = 900
    # Only enable for tests or a trusted intranet: it disables the SSRF guard.
    allow_private_fetch_targets: bool = False

    # --- graph behaviour ---
    results_per_subtopic: int = 8
    min_relevant_results: int = 4
    max_search_attempts: int = 2
    relevance_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    # How many of the theme's own terms must appear in an article's headline or
    # lede before it can be selected, whatever the LLM scored it. Capped by how
    # many terms the theme actually has, and relaxed to 1 on a widened retry.
    # 0 disables the gate entirely.
    min_topic_terms: int = Field(default=2, ge=0, le=5)
    enable_factcheck: bool = True
    graph_recursion_limit: int = 50

    # --- scheduler ---
    enable_scheduler: bool = True
    scheduler_tick_seconds: int = 60

    # --- storage ---
    data_dir: str = "./data"
    checkpoint_db: str = "./data/checkpoints.sqlite"
    runs_db: str = "./data/runs.sqlite"
    run_history_limit: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("rss_feeds", "cors_origins", "search_providers", mode="before")
    @classmethod
    def _parse_list(cls, value: object) -> object:
        """Accept `A,B` as well as `["A","B"]` — plain CSV is far easier in a .env."""

        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"expected a JSON array or comma-separated list: {exc}") from exc
        return [item.strip() for item in text.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
