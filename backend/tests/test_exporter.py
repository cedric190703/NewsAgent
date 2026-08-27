"""Export rendering. Newsletter text comes from third-party pages by way of the
model, so escaping and URL-scheme filtering are correctness requirements."""

import pytest

from app.graph.state import ArticleScores, Conflict, KeyFact, Newsletter
from app.services.exporter import ExportError, to_html, to_markdown, to_pdf
from tests.conftest import make_newsletter


class TestMarkdown:
    def test_structure_is_rendered(self):
        markdown = to_markdown(make_newsletter())
        assert markdown.startswith("# Reef digest")
        assert "## Recovery" in markdown
        assert "### Story 1" in markdown
        assert "- Bullet 1" in markdown
        assert "## Sources" in markdown

    def test_quotes_are_rendered_as_blockquotes(self):
        assert '> "Quote 1"' in to_markdown(make_newsletter())

    def test_conflicts_are_listed(self):
        newsletter = make_newsletter(
            conflicts=[Conflict(claim="Figures differ", severity="high", note="A vs B")]
        )
        markdown = to_markdown(newsletter)
        assert "**[high]** Figures differ — A vs B" in markdown

    def test_brackets_in_titles_cannot_close_a_link_early(self):
        newsletter = make_newsletter()
        newsletter.sources[0].title = "Evil ](https://attacker.test) title"
        markdown = to_markdown(newsletter)
        # The closing bracket is backslash-escaped, so the injected URL
        # stays plain text instead of terminating the source link.
        assert r"Evil \](https://attacker.test) title" in markdown

    def test_non_http_fact_urls_are_not_linked(self):
        newsletter = make_newsletter()
        newsletter.sections[0].items[0].key_facts = [
            KeyFact(claim="c", quote="q", url="javascript:alert(1)")
        ]
        assert "javascript:" not in to_markdown(newsletter)

    def test_empty_newsletter_renders_without_error(self):
        assert to_markdown(Newsletter(title="Empty")).startswith("# Empty")


class TestHtml:
    def test_document_is_well_formed(self):
        html = to_html(make_newsletter())
        assert html.startswith("<!doctype html>")
        assert "<title>Reef digest</title>" in html
        assert html.rstrip().endswith("</html>")

    def test_html_in_model_output_is_escaped(self):
        newsletter = make_newsletter(title="<script>alert('xss')</script>")
        html = to_html(newsletter)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_attribute_breaking_quotes_are_escaped(self):
        newsletter = make_newsletter()
        newsletter.sections[0].items[0].image_url = 'https://x.test/a.jpg" onerror="alert(1)'
        html = to_html(newsletter)
        assert 'onerror="alert(1)"' not in html

    def test_javascript_urls_are_not_turned_into_links(self):
        newsletter = make_newsletter()
        newsletter.sources[0].url = "javascript:alert(1)"
        html = to_html(newsletter)
        assert 'href="javascript:' not in html

    def test_external_links_are_noopener(self):
        html = to_html(make_newsletter())
        assert 'rel="noopener noreferrer"' in html

    def test_notes_render_as_notices(self):
        html = to_html(make_newsletter(notes=["Fewer sources than requested."]))
        assert "Fewer sources than requested." in html

    def test_dark_mode_styles_are_included(self):
        assert "prefers-color-scheme: dark" in to_html(make_newsletter())


class TestPdf:
    def test_missing_weasyprint_raises_an_actionable_export_error(self):
        try:
            import weasyprint  # noqa: F401
        except ImportError:
            with pytest.raises(ExportError) as excinfo:
                to_pdf(make_newsletter())
            assert "weasyprint" in str(excinfo.value).lower()
        else:
            assert to_pdf(make_newsletter())[:4] == b"%PDF"


def test_scores_are_shown_in_markdown():
    newsletter = make_newsletter()
    newsletter.sections[0].items[0].scores = ArticleScores(composite=0.91)
    assert "score 0.91" in to_markdown(newsletter)
