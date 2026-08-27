"""Shared fixtures.

Settings are read into a module-level singleton at import time, so the
environment has to be set *before* anything under `app.` is imported. pytest
loads conftest first, which makes this the only reliable place to do it.
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="newsagent-tests-")

os.environ.update(
    ENVIRONMENT="test",
    LLM_PROVIDER="mock",
    SEARCH_PROVIDERS="mock",
    LOG_LEVEL="WARNING",
    ENABLE_SCHEDULER="false",
    ENABLE_ARTICLE_EXTRACTION="false",
    DATA_DIR=_TMP,
    RUNS_DB=os.path.join(_TMP, "runs.sqlite"),
    CHECKPOINT_DB=os.path.join(_TMP, "checkpoints.sqlite"),
)

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.graph.state import (  # noqa: E402
    ArticleScores,
    ArticleSummary,
    KeyFact,
    Newsletter,
    NewsletterSection,
    RawArticle,
    RunConfig,
    SourceRef,
    article_id,
)
from app.services import store  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_database(tmp_path, monkeypatch):
    """Give every test its own SQLite files so ordering cannot leak state."""

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "runs_db", str(tmp_path / "runs.sqlite"))
    monkeypatch.setattr(settings, "checkpoint_db", str(tmp_path / "checkpoints.sqlite"))
    yield


@pytest.fixture
async def db():
    await store.init_db()
    try:
        yield store
    finally:
        await store.close_db()


@pytest.fixture
async def client():
    """An ASGI client with the app's real lifespan (DB, scheduler, shutdown)."""

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=120
    ) as http_client:
        yield http_client


@pytest.fixture
def run_config() -> RunConfig:
    return RunConfig(
        theme="coral reef restoration",
        subtopic_count=2,
        max_sources=4,
        providers=["mock"],
    )


def make_article(
    url: str = "https://reuters.com/story-one",
    title: str = "Reef recovery milestone reached ahead of schedule",
    body: str = "",
    **kwargs,
) -> RawArticle:
    defaults: dict = {
        "id": article_id(url),
        "subtopic_id": "sub-1",
        "url": url,
        "title": title,
        "source_name": "Reuters",
        "snippet": body[:200],
        "content": body,
    }
    defaults.update(kwargs)
    return RawArticle(**defaults)


def make_summary(article_idx: int = 1, **kwargs) -> ArticleSummary:
    url = kwargs.pop("url", f"https://reuters.com/story-{article_idx}")
    defaults: dict = {
        "article_id": article_id(url),
        "subtopic_id": "sub-1",
        "headline": f"Story {article_idx}",
        "bullets": [f"Bullet {article_idx}"],
        "key_facts": [
            KeyFact(claim=f"Claim {article_idx}", quote=f"Quote {article_idx}", url=url)
        ],
        "url": url,
        "source_name": "Reuters",
        "scores": ArticleScores(composite=0.8),
    }
    defaults.update(kwargs)
    return ArticleSummary(**defaults)


def make_newsletter(**kwargs) -> Newsletter:
    summary = make_summary()
    defaults: dict = {
        "title": "Reef digest",
        "subtitle": "Two angles",
        "intro": "An intro paragraph.",
        "sections": [
            NewsletterSection(
                subtopic_id="sub-1", title="Recovery", blurb="Blurb.", items=[summary]
            )
        ],
        "sources": [
            SourceRef(
                article_id=summary.article_id,
                title=summary.headline,
                url=summary.url,
                source_name=summary.source_name,
            )
        ],
        "outro": "An outro.",
    }
    defaults.update(kwargs)
    return Newsletter(**defaults)
