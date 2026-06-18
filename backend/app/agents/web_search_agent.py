from app.schemas.news import NewsQueryRequest, NewsSource, SourceType


class WebSearchAgent:
    async def fetch(self, request: NewsQueryRequest) -> list[NewsSource]:
        return [
            NewsSource(
                title=f"Web search placeholder for {request.topic}",
                source_type=SourceType.WEB,
                publisher="Web search provider",
                summary=(
                    "Web search will connect to a search API or scraping-safe "
                    "provider once a source strategy is selected."
                ),
                relevance_score=0.65,
            )
        ]
