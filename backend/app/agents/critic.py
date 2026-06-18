from app.schemas.news import NewsQueryRequest, NewsSource


class CriticAgent:
    def review(
        self,
        request: NewsQueryRequest,
        draft: str,
        sources: list[NewsSource],
    ) -> list[str]:
        notes: list[str] = []

        if not sources:
            notes.append("No sources were available, so confidence is limited.")

        if request.include_citations and not any(source.url for source in sources):
            notes.append("No source URLs are attached yet; citations should be improved.")

        if len(draft.strip()) < 200:
            notes.append("The generated answer is short and may need deeper analysis.")

        if not notes:
            notes.append("The answer passed the initial structure and source checks.")

        return notes
