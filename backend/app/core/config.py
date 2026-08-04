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
            # General news
            "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "https://feeds.bbci.co.uk/news/science-environment/rss.xml",
            "https://feeds.bbci.co.uk/news/health/rss.xml",
            "https://www.theverge.com/rss/index.xml",
            "https://feeds.arstechnica.com/arstechnica/index",
            "https://www.wired.com/feed/rss",
            "https://www.theguardian.com/world/rss",
            "https://www.theguardian.com/science/rss",
            "https://www.theguardian.com/technology/rss",
            "https://www.theguardian.com/society/health/rss",
            "https://feeds.reuters.com/reuters/topNews",
            "https://feeds.reuters.com/reuters/businessNews",
            "https://feeds.reuters.com/reuters/technologyNews",
            "https://hnrss.org/frontpage",
            "https://www.techmeme.com/feed.xml",
            "https://feeds.feedburner.com/TechCrunch/",
            "https://www.engadget.com/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
            # Science / research
            "https://feeds.nature.com/nature/rss/current",
            "https://science.sciencemag.org/rss/current.xml",
            "https://www.sciencedaily.com/rss/all.xml",
            "https://www.sciencedaily.com/rss/health_medicine.xml",
            "https://www.sciencedaily.com/rss/computers_math.xml",
            "https://phys.org/rss-feed/breaking/",
            "https://www.eurekalert.org/rss/technology_engineering.xml",
            "https://www.eurekalert.org/rss/medicine_health.xml",
            # Space / energy
            "https://spacenews.com/feed/",
            # AI / ML focused
            "https://news.google.com/rss/search?q=AI+artificial+intelligence+machine+learning&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=AI+healthcare+medical&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=artificial+intelligence+medicine+hospital&hl=en-US&gl=US&ceid=US:en",
            # Health / medical focused
            "https://www.medscape.com/rss/medicalstudents_headlines",
            "https://www.statnews.com/feed/",
            "https://www.fiercehealthcare.com/rss/xml",
            "https://www.healthcareitnews.com/rss.xml",
            "https://www.mobihealthnews.com/rss.xml",
        ]
    )

    # --- admin ---
    admin_password: str = "admin123"
    # Secret key for signing subscriber auth tokens (change in production!)
    secret_key: str = "change-me-in-production"

    # --- email / mailing list ---
    # SMTP (optional — used if resend_api_key is not set)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Good News Agent"
    smtp_use_tls: bool = True
    # Resend API (preferred — set RESEND_API_KEY to use instead of SMTP)
    resend_api_key: str = ""

    # --- fetching / extraction ---
    source_fetch_timeout_seconds: int = 15
    http_user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    enable_article_extraction: bool = True
    min_content_chars: int = 400
    max_article_chars: int = 16000

    # --- graph behaviour ---
    results_per_subtopic: int = 20
    min_relevant_results: int = 2
    max_search_attempts: int = 2
    relevance_threshold: float = 0.30
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
