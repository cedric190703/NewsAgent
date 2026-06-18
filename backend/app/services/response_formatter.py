import re

from app.schemas.news import NewsQueryRequest, NewsQueryResponse, NewsSource


class ResponseFormatter:
    def format_response(
        self,
        request: NewsQueryRequest,
        draft: str,
        sources: list[NewsSource],
        critic_notes: list[str],
    ) -> NewsQueryResponse:
        key_points = self._extract_bullets(draft)

        if not key_points:
            key_points = [
                source.summary or source.title
                for source in sources[:3]
            ] or ["No key points could be extracted yet."]

        executive_summary = self._first_paragraph(draft)
        confidence = "medium" if sources else "low"

        return NewsQueryResponse(
            topic=request.topic,
            output_format=request.output_format,
            executive_summary=executive_summary,
            key_points=key_points[:5],
            analysis=draft.strip(),
            sources=sources if request.include_citations else [],
            confidence=confidence,
            suggested_followups=[
                f"What changed recently about {request.topic}?",
                f"Which sources are most reliable for {request.topic}?",
                f"What are the risks and opportunities around {request.topic}?",
            ],
            critic_notes=critic_notes,
        )

    def _first_paragraph(self, text: str) -> str:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return "No summary was generated."
        return re.sub(r"^(Executive Summary|Summary)\s*:?\s*", "", paragraphs[0]).strip()

    def _extract_bullets(self, text: str) -> list[str]:
        bullets: list[str] = []
        for line in text.splitlines():
            clean = line.strip()
            if clean.startswith(("- ", "* ")):
                bullets.append(clean[2:].strip())
        return bullets
