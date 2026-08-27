from app.search import extract


class TestHtmlToText:
    def test_tags_are_stripped_and_entities_decoded(self):
        assert extract.html_to_text("<p>Hello &amp; welcome</p>") == "Hello & welcome"

    def test_scripts_and_styles_are_removed(self):
        html = "<p>Keep</p><script>var evil = 1;</script><style>.a{color:red}</style>"
        text = extract.html_to_text(html)
        assert "Keep" in text
        assert "evil" not in text and "color:red" not in text

    def test_comments_are_removed(self):
        assert "hidden" not in extract.html_to_text("<p>Shown</p><!-- hidden -->")

    def test_block_elements_become_line_breaks(self):
        assert extract.html_to_text("<p>One</p><p>Two</p>").splitlines() == ["One", "Two"]

    def test_empty_input_is_safe(self):
        assert extract.html_to_text("") == ""


class TestContentScoping:
    def _page(self, body: str) -> str:
        return (
            "<html><body><nav>Home About Contact Subscribe</nav>"
            "<header>Cookie banner accept all</header>"
            f"{body}"
            "<footer>Copyright 2026 Terms Privacy</footer></body></html>"
        )

    def test_article_landmark_is_preferred_over_page_chrome(self):
        story = "<article><p>" + ("The reef survey found measurable recovery. " * 20) + "</p></article>"
        text = extract.html_to_text(self._page(story), scope_to_content=True)
        assert "reef survey" in text
        assert "Cookie banner" not in text
        assert "Copyright 2026" not in text

    def test_main_landmark_is_used_when_there_is_no_article(self):
        story = "<main><p>" + ("Coral restoration progressed this quarter. " * 20) + "</p></main>"
        text = extract.html_to_text(self._page(story), scope_to_content=True)
        assert "Coral restoration" in text
        assert "Subscribe" not in text

    def test_a_tiny_article_teaser_does_not_replace_the_page(self):
        page = self._page("<article><p>Teaser</p></article><p>" + ("Real story text. " * 40) + "</p>")
        text = extract.html_to_text(page, scope_to_content=True)
        assert "Real story text" in text

    def test_chrome_is_dropped_even_without_a_landmark(self):
        text = extract.html_to_text(self._page("<p>Body text here.</p>"), scope_to_content=True)
        assert "Body text here." in text
        assert "Copyright 2026" not in text


class TestOgImage:
    def test_property_form_is_found(self):
        html = '<meta property="og:image" content="https://x.test/a.jpg">'
        assert extract.find_og_image(html) == "https://x.test/a.jpg"

    def test_name_form_is_found(self):
        html = "<meta name='og:image' content='https://x.test/b.jpg'>"
        assert extract.find_og_image(html) == "https://x.test/b.jpg"

    def test_missing_tag_returns_none(self):
        assert extract.find_og_image("<html></html>") is None
