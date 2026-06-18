from fastapi import APIRouter, Depends, status

from app.schemas.news import FeedbackRequest, NewsQueryRequest, NewsQueryResponse
from app.services.pipeline import NewsPipeline, get_news_pipeline

router = APIRouter()


@router.post("/query", response_model=NewsQueryResponse)
async def query_news(
    request: NewsQueryRequest,
    pipeline: NewsPipeline = Depends(get_news_pipeline),
) -> NewsQueryResponse:
    return await pipeline.run(request)


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(request: FeedbackRequest) -> dict[str, str]:
    # Persistence will be added once a database is selected.
    return {"status": "accepted", "result_id": str(request.result_id)}
