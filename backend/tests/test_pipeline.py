import asyncio

from app.providers.mock import MockProvider
from app.schemas.news import NewsQueryRequest, SourceType
from app.services.pipeline import NewsPipeline


def test_pipeline_returns_structured_response() -> None:
    pipeline = NewsPipeline(provider=MockProvider())

    async def run_pipeline():
        return await pipeline.run(
            NewsQueryRequest(
                topic="AI regulation",
                sources=[SourceType.RSS, SourceType.WEB],
            )
        )

    response = asyncio.run(run_pipeline())

    assert response.topic == "AI regulation"
    assert response.executive_summary
    assert response.key_points
    assert response.sources
