from app.providers.base import ChatMessage, LLMProvider
from app.schemas.news import NewsQueryRequest, NewsSource


class WriterAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def write(self, request: NewsQueryRequest, sources: list[NewsSource]) -> str:
        source_context = "\n".join(
            f"- {source.title}: {source.summary or 'No summary available.'}"
            for source in sources
        )

        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a professional AI news analyst. Produce concise, "
                    "structured, factual briefings with clear analysis."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Topic: {request.topic}\n"
                    f"Section: {request.section or 'general'}\n"
                    f"Output format: {request.output_format.value}\n"
                    f"Depth: {request.depth}\n\n"
                    f"Sources:\n{source_context}\n\n"
                    "Write an executive summary, key points, and analysis."
                ),
            ),
        ]
        return await self._provider.generate(messages)
