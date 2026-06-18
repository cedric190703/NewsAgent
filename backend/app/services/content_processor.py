from app.schemas.news import NewsSource


class ContentProcessor:
    def process(self, sources: list[NewsSource]) -> list[NewsSource]:
        seen: set[str] = set()
        unique_sources: list[NewsSource] = []

        for source in sources:
            key = (str(source.url) if source.url else source.title).lower()
            if key in seen:
                continue
            seen.add(key)
            unique_sources.append(source)

        return sorted(
            unique_sources,
            key=lambda source: source.relevance_score,
            reverse=True,
        )
