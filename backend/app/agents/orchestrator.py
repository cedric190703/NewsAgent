from app.schemas.news import NewsQueryRequest, SourceType


class OrchestratorAgent:
    def plan(self, request: NewsQueryRequest) -> list[SourceType]:
        if request.sources:
            return request.sources
        return [SourceType.RSS]
