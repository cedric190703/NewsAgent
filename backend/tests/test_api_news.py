"""The synchronous briefing endpoint and feedback persistence."""

import pytest

pytestmark = pytest.mark.asyncio

QUERY = {
    "topic": "coral reef restoration",
    "depth": 2,
    "max_sources": 4,
    "providers": ["mock"],
}


class TestQuery:
    async def test_a_briefing_is_returned_with_real_sources(self, client):
        response = await client.post("/api/news/query", json=QUERY)
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["topic"] == QUERY["topic"]
        assert body["executive_summary"]
        assert body["key_points"]
        assert body["sources"]
        assert body["confidence"] in {"high", "medium", "low"}
        assert body["suggested_followups"]
        assert body["critic_notes"]

    async def test_the_briefing_is_recorded_in_run_history(self, client):
        run_id = (await client.post("/api/news/query", json=QUERY)).json()["run_id"]
        detail = (await client.get(f"/api/runs/{run_id}")).json()
        assert detail["status"] == "done"
        assert detail["source"] == "query"

    async def test_citations_can_be_switched_off(self, client):
        response = await client.post(
            "/api/news/query", json={**QUERY, "include_citations": False}
        )
        assert response.json()["sources"] == []

    async def test_source_list_format_omits_the_analysis_body(self, client):
        response = await client.post(
            "/api/news/query", json={**QUERY, "output_format": "source_list"}
        )
        body = response.json()
        assert body["analysis"] == ""
        assert body["sources"]

    async def test_key_points_carry_their_publisher(self, client):
        points = (await client.post("/api/news/query", json=QUERY)).json()["key_points"]
        assert all(point.endswith(")") for point in points)

    @pytest.mark.parametrize(
        "payload",
        [{"topic": "ab"}, {"topic": "valid topic", "depth": 9}, {"topic": "valid topic", "days": 0}],
    )
    async def test_invalid_requests_are_rejected(self, client, payload):
        assert (await client.post("/api/news/query", json=payload)).status_code == 422


class TestFeedback:
    async def test_feedback_is_persisted_and_summarised(self, client):
        run_id = (await client.post("/api/news/query", json=QUERY)).json()["run_id"]

        created = await client.post(
            "/api/news/feedback", json={"run_id": run_id, "rating": 4, "comment": "useful"}
        )
        assert created.status_code == 201
        assert created.json()["feedback_id"]

        listing = (await client.get("/api/news/feedback")).json()
        assert listing["summary"] == {"count": 1, "average_rating": 4.0}
        assert listing["items"][0]["comment"] == "useful"

    async def test_feedback_can_be_filtered_by_run(self, client):
        run_id = (await client.post("/api/news/query", json=QUERY)).json()["run_id"]
        await client.post("/api/news/feedback", json={"run_id": run_id, "rating": 5})
        listing = (await client.get("/api/news/feedback", params={"run_id": run_id})).json()
        assert len(listing["items"]) == 1

    async def test_feedback_for_an_unknown_run_is_404(self, client):
        response = await client.post(
            "/api/news/feedback", json={"run_id": "nope", "rating": 5}
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("rating", [0, 6, -1])
    async def test_out_of_range_ratings_are_rejected(self, client, rating):
        assert (await client.post("/api/news/feedback", json={"rating": rating})).status_code == 422

    async def test_anonymous_feedback_without_a_run_is_accepted(self, client):
        assert (await client.post("/api/news/feedback", json={"rating": 3})).status_code == 201
