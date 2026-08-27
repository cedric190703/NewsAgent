from datetime import datetime, timedelta, timezone

import pytest

from app.graph import scoring
from app.graph.state import ArticleScores, GoodNewsMode
from tests.conftest import make_article

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


class TestRelevance:
    def test_title_overlap_beats_body_only_overlap(self):
        on_topic = make_article(title="Coral reef restoration hits milestone")
        off_topic = make_article(
            title="Local bakery wins award", body="coral reef restoration " * 5
        )
        theme = "coral reef restoration"
        assert scoring.relevance_score(theme, theme, on_topic) > scoring.relevance_score(
            theme, theme, off_topic
        )

    def test_unrelated_article_scores_near_zero(self):
        article = make_article(title="Stock markets close flat")
        assert scoring.relevance_score("coral reef restoration", "coral", article) < 0.2

    def test_empty_theme_is_neutral(self):
        assert scoring.relevance_score("", "", make_article()) == 0.5

    def test_score_stays_in_range(self):
        article = make_article(title="coral reef restoration coral reef restoration")
        assert 0.0 <= scoring.relevance_score("coral reef", "coral reef", article) <= 1.0


class TestRecency:
    def test_fresh_article_scores_near_one(self):
        assert scoring.recency_score(NOW, NOW) == pytest.approx(1.0)

    def test_one_half_life_halves_the_score(self):
        week_old = NOW - timedelta(days=7)
        assert scoring.recency_score(week_old, NOW) == pytest.approx(0.5, abs=0.01)

    def test_missing_date_is_penalised_but_not_zero(self):
        assert 0.0 < scoring.recency_score(None, NOW) < 0.5

    def test_naive_datetimes_are_treated_as_utc(self):
        naive = datetime(2026, 8, 27)
        assert scoring.recency_score(naive, NOW) == pytest.approx(1.0)

    def test_future_dates_do_not_exceed_one(self):
        assert scoring.recency_score(NOW + timedelta(days=5), NOW) <= 1.0


class TestCredibility:
    def test_tier_one_outranks_tier_two_outranks_unknown(self):
        tier_one = scoring.credibility_score(make_article(url="https://reuters.com/a"))
        tier_two = scoring.credibility_score(make_article(url="https://theverge.com/a"))
        unknown = scoring.credibility_score(make_article(url="https://randomsite.xyz/a"))
        assert tier_one > tier_two > unknown

    def test_low_trust_markers_cap_the_score(self):
        assert scoring.credibility_score(make_article(url="https://x.blogspot.com/a")) <= 0.35

    def test_government_and_academic_domains_rank_high(self):
        assert scoring.credibility_score(make_article(url="https://noaa.gov/a")) >= 0.85
        assert scoring.credibility_score(make_article(url="https://mit.edu/a")) >= 0.85

    def test_plain_http_is_penalised(self):
        secure = scoring.credibility_score(make_article(url="https://randomsite.xyz/a"))
        insecure = scoring.credibility_score(make_article(url="http://randomsite.xyz/a"))
        assert insecure < secure


class TestGoodnessAxes:
    def test_positive_outcome_scores_above_neutral(self):
        good = make_article(title="Reef recovery: breakthrough restored 40% of coral")
        assert scoring.valence_score(good) > 0.5

    def test_negative_outcome_scores_below_neutral(self):
        bad = make_article(title="Reef collapse: disaster kills coral, warns study")
        assert scoring.valence_score(bad) < 0.5

    def test_neutral_text_is_exactly_neutral(self):
        assert scoring.valence_score(make_article(title="Reef survey published")) == 0.5

    def test_sourced_reporting_outscores_clickbait(self):
        sourced = make_article(
            title="Study finds 34 percent improvement",
            body="According to the peer-reviewed study, researchers analysed data "
            "published in the report. The survey covered 4,000 participants.",
        )
        clickbait = make_article(
            title="You won't believe this shocking reef trick",
            body="Experts are stunned. This one trick changed everything.",
        )
        assert scoring.signal_score(sourced) > scoring.signal_score(clickbait)

    def test_listicle_titles_are_penalised(self):
        listicle = make_article(title="7 things nobody tells you about reefs")
        plain = make_article(title="Reef restoration progress reviewed")
        assert scoring.signal_score(listicle) < scoring.signal_score(plain)


class TestComposite:
    def _scores(self):
        return ArticleScores(
            relevance=0.8, recency=0.6, credibility=0.9,
            goodness_valence=1.0, goodness_signal=0.2,
        )

    def test_mode_changes_the_ranking_not_the_measurements(self):
        scores = self._scores()
        uplifting = scoring.composite_score(scores, GoodNewsMode.UPLIFTING)
        high_signal = scoring.composite_score(scores, GoodNewsMode.HIGH_SIGNAL)
        assert uplifting > high_signal
        assert scores.goodness_valence == 1.0  # unchanged by weighting

    def test_high_signal_mode_ignores_valence_entirely(self):
        cheerful = ArticleScores(relevance=0.5, goodness_valence=1.0, goodness_signal=0.5)
        grim = ArticleScores(relevance=0.5, goodness_valence=0.0, goodness_signal=0.5)
        mode = GoodNewsMode.HIGH_SIGNAL
        assert scoring.composite_score(cheerful, mode) == scoring.composite_score(grim, mode)

    @pytest.mark.parametrize("mode", list(GoodNewsMode))
    def test_composite_stays_in_range(self, mode):
        perfect = ArticleScores(
            relevance=1.0, recency=1.0, credibility=1.0,
            goodness_valence=1.0, goodness_signal=1.0,
        )
        assert 0.0 <= scoring.composite_score(perfect, mode) <= 1.0
        assert scoring.composite_score(ArticleScores(), mode) >= 0.0

    def test_explain_lists_only_the_active_axes(self):
        reasons = scoring.explain(self._scores(), GoodNewsMode.HIGH_SIGNAL)
        assert not any("constructive" in reason for reason in reasons)
        assert any("signal" in reason for reason in reasons)
