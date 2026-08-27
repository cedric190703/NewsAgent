"""RSS/Atom parsing, keyword filtering, and the feed cache that prevents a
per-sub-topic fetch stampede."""

from datetime import datetime, timezone

import pytest

from app.search.base import SearchQuery
from app.search.rss import RssProvider, _feed_cache, _parse_date

RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Reef Wire</title>
    <item>
      <title>Coral reef restoration reaches milestone</title>
      <link>https://reefwire.test/coral-milestone</link>
      <description>&lt;p&gt;A coral reef restoration project hit its target.&lt;/p&gt;</description>
      <pubDate>Wed, 26 Aug 2026 10:00:00 GMT</pubDate>
      <media:content url="https://reefwire.test/img.jpg"/>
    </item>
    <item>
      <title>Local bakery wins prize</title>
      <link>https://reefwire.test/bakery</link>
      <description>Unrelated content.</description>
      <pubDate>Tue, 25 Aug 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>No link here</title>
      <description>Should be skipped.</description>
    </item>
  </channel>
</rss>"""

ATOM_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Reefs</title>
  <entry>
    <title>Reef recovery study published</title>
    <link rel="edit" href="https://atom.test/edit/1"/>
    <link rel="alternate" href="https://atom.test/reef-recovery"/>
    <summary>A study on reef recovery.</summary>
    <published>2026-08-26T09:00:00Z</published>
  </entry>
</feed>"""


@pytest.fixture(autouse=True)
def _clear_feed_cache():
    _feed_cache.clear()
    yield
    _feed_cache.clear()


def provider() -> RssProvider:
    return RssProvider(["https://reefwire.test/feed.xml"])


class TestParsing:
    def test_rss_items_become_hits(self):
        hits = provider()._parse(RSS_FEED, "https://reefwire.test/feed.xml")
        assert [hit.title for hit in hits] == [
            "Coral reef restoration reaches milestone",
            "Local bakery wins prize",
        ]

    def test_html_in_descriptions_is_flattened(self):
        hits = provider()._parse(RSS_FEED, "f")
        assert hits[0].snippet == "A coral reef restoration project hit its target."

    def test_feed_title_becomes_the_source_name(self):
        assert provider()._parse(RSS_FEED, "f")[0].source_name == "Reef Wire"

    def test_media_content_becomes_the_image(self):
        assert provider()._parse(RSS_FEED, "f")[0].image_url == "https://reefwire.test/img.jpg"

    def test_entries_without_a_link_are_skipped(self):
        assert all(hit.url for hit in provider()._parse(RSS_FEED, "f"))

    def test_atom_alternate_link_is_preferred_over_edit_link(self):
        hits = provider()._parse(ATOM_FEED, "f")
        assert hits[0].url == "https://atom.test/reef-recovery"

    def test_malformed_xml_yields_no_hits_instead_of_raising(self):
        assert provider()._parse("<not xml", "f") == []


class TestFiltering:
    def _hits(self):
        return provider()._parse(RSS_FEED, "f")

    def test_keyword_match_drops_unrelated_items(self):
        query = SearchQuery(query="coral reef restoration")
        titles = [hit.title for hit in provider()._filter(self._hits(), query)]
        assert titles == ["Coral reef restoration reaches milestone"]

    def test_date_window_excludes_older_items(self):
        query = SearchQuery(
            query="coral", date_from=datetime(2026, 8, 27, tzinfo=timezone.utc)
        )
        assert provider()._filter(self._hits(), query) == []

    def test_duplicate_urls_are_collapsed(self):
        doubled = self._hits() * 2
        query = SearchQuery(query="coral")
        assert len(provider()._filter(doubled, query)) == 1

    def test_results_are_sorted_by_overlap_then_recency(self):
        query = SearchQuery(query="reef")
        results = provider()._filter(self._hits(), query)
        assert results[0].title == "Coral reef restoration reaches milestone"


class TestFeedCache:
    async def test_feeds_are_fetched_once_across_concurrent_searches(self, monkeypatch):
        import asyncio

        calls = 0

        async def fake_fetch_text(url, **kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return RSS_FEED

        monkeypatch.setattr("app.search.rss.fetch_text", fake_fetch_text)
        query = SearchQuery(query="coral reef restoration")
        await asyncio.gather(*(provider().search(query) for _ in range(5)))
        assert calls == 1

    async def test_a_failed_feed_does_not_break_the_search(self, monkeypatch):
        async def fake_fetch_text(url, **kwargs):
            return None

        monkeypatch.setattr("app.search.rss.fetch_text", fake_fetch_text)
        assert await provider().search(SearchQuery(query="coral")) == []

    async def test_enrichment_does_not_mutate_the_cached_entries(self, monkeypatch):
        async def fake_fetch_text(url, **kwargs):
            return RSS_FEED

        monkeypatch.setattr("app.search.rss.fetch_text", fake_fetch_text)
        query = SearchQuery(query="coral reef restoration")
        first = await provider().search(query)
        first[0].content = "MUTATED"
        second = await provider().search(query)
        assert second[0].content != "MUTATED"


class TestDateParsing:
    def test_rfc_2822(self):
        assert _parse_date("Wed, 26 Aug 2026 10:00:00 GMT") == datetime(
            2026, 8, 26, 10, 0, tzinfo=timezone.utc
        )

    def test_iso_8601_with_z(self):
        assert _parse_date("2026-08-26T09:00:00Z") == datetime(
            2026, 8, 26, 9, 0, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("value", [None, "", "not a date"])
    def test_unparseable_values_return_none(self, value):
        assert _parse_date(value) is None
