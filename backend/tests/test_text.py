"""Topic-term extraction and the on-topic requirement it feeds."""


from app.core.text import required_term_count, terms, topic_terms
from app.graph.scoring import topical_terms_matched
from tests.conftest import make_article


class TestTerms:
    def test_short_words_are_dropped(self):
        assert terms("AI in the ocean") == {"the", "ocean"}

    def test_case_and_punctuation_are_normalised(self):
        assert terms("Coral-Reef, RESTORATION!") == {"coral", "reef", "restoration"}

    def test_stopwords_are_removed_from_topic_terms(self):
        assert topic_terms("the latest news about coral reefs") == {"coral", "reefs"}

    def test_a_theme_of_only_stopwords_has_no_topic_terms(self):
        assert topic_terms("the latest news update") == set()


class TestRequiredTermCount:
    def test_a_single_word_theme_can_only_require_one(self):
        assert required_term_count("ocean", maximum=2) == 1

    def test_a_compound_theme_requires_both_words(self):
        """The bug this exists to stop: a car review matching only 'technology'."""

        assert required_term_count("climate technology", maximum=2) == 2

    def test_a_long_theme_is_capped_at_the_maximum(self):
        assert required_term_count("coral reef restoration funding", maximum=2) == 2

    def test_a_widened_retry_relaxes_to_one_term(self):
        assert required_term_count("climate technology", maximum=2, widened=True) == 1

    def test_zero_maximum_disables_the_gate(self):
        assert required_term_count("climate technology", maximum=0) == 0

    def test_a_theme_with_no_topic_terms_requires_nothing(self):
        assert required_term_count("the news", maximum=2) == 0


class TestTopicalTermsMatched:
    def test_a_headline_mentioning_the_topic_matches(self):
        article = make_article(title="Climate technology funding reaches record high")
        assert topical_terms_matched("climate technology", article) == 2

    def test_a_lede_mention_counts(self):
        article = make_article(
            title="Record funding announced",
            body="New climate technology projects secured backing this quarter.",
        )
        assert topical_terms_matched("climate technology", article) == 2

    def test_the_article_body_is_deliberately_ignored(self):
        """A fetched page carries nav and related links; only the lede is evidence."""

        article = make_article(
            title="The Porsche 911 GT3 punches above its weight",
            body="climate technology " * 100,
            snippet="",
        )
        assert topical_terms_matched("climate technology", article) == 0

    def test_a_partial_match_is_reported_as_partial(self):
        article = make_article(title="Technology firms report earnings")
        assert topical_terms_matched("climate technology", article) == 1

    def test_a_theme_with_no_topic_terms_never_blocks(self):
        assert topical_terms_matched("the news", make_article()) == 1
