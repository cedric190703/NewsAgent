from app.schemas.news import NewsQueryRequest, NewsSource, SourceType


class RAGKnowledgeAgent:
    async def fetch(self, request: NewsQueryRequest) -> list[NewsSource]:
        return [
            NewsSource(
                title=f"Knowledge-base placeholder for {request.topic}",
                source_type=SourceType.KNOWLEDGE_BASE,
                publisher="Local knowledge base",
                summary=(
                    "RAG retrieval will connect to embeddings and a vector store "
                    "after the storage choice is validated."
                ),
                relevance_score=0.6,
            )
        ]
