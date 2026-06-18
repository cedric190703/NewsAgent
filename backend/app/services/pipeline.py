from functools import lru_cache

from app.agents.critic import CriticAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.rag_agent import RAGKnowledgeAgent
from app.agents.rss_agent import RSSFeedAgent
from app.agents.web_search_agent import WebSearchAgent
from app.agents.writer import WriterAgent
from app.providers.base import LLMProvider
from app.providers.factory import get_llm_provider
from app.schemas.news import NewsQueryRequest, NewsQueryResponse, SourceType
from app.services.content_processor import ContentProcessor
from app.services.response_formatter import ResponseFormatter


class NewsPipeline:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        provider = provider or get_llm_provider()
        self._orchestrator = OrchestratorAgent()
        self._rss_agent = RSSFeedAgent()
        self._web_agent = WebSearchAgent()
        self._rag_agent = RAGKnowledgeAgent()
        self._processor = ContentProcessor()
        self._writer = WriterAgent(provider)
        self._critic = CriticAgent()
        self._formatter = ResponseFormatter()

    async def run(self, request: NewsQueryRequest) -> NewsQueryResponse:
        planned_sources = self._orchestrator.plan(request)
        collected_sources = []

        if SourceType.RSS in planned_sources:
            collected_sources.extend(await self._rss_agent.fetch(request))
        if SourceType.WEB in planned_sources:
            collected_sources.extend(await self._web_agent.fetch(request))
        if SourceType.KNOWLEDGE_BASE in planned_sources:
            collected_sources.extend(await self._rag_agent.fetch(request))

        processed_sources = self._processor.process(collected_sources)
        draft = await self._writer.write(request, processed_sources)
        critic_notes = self._critic.review(request, draft, processed_sources)

        return self._formatter.format_response(
            request=request,
            draft=draft,
            sources=processed_sources,
            critic_notes=critic_notes,
        )


@lru_cache
def get_news_pipeline() -> NewsPipeline:
    return NewsPipeline()
