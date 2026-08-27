"""Run, bookmark and export endpoints, including the contracts the frontend calls."""

import json

import pytest

pytestmark = pytest.mark.asyncio

RUN_BODY = {
    "theme": "coral reef restoration",
    "subtopic_count": 2,
    "max_sources": 4,
    "providers": ["mock"],
}


async def create_run(client, **overrides) -> str:
    response = await client.post("/api/runs", json={**RUN_BODY, **overrides})
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


async def drain_stream(client, run_id: str) -> dict[str, list]:
    events: dict[str, list] = {}
    current = ""
    async with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.setdefault(current, []).append(json.loads(line[6:]))
                current = ""
    return events


class TestCreateAndStream:
    async def test_creating_a_run_returns_an_id(self, client):
        assert len(await create_run(client)) == 32

    async def test_a_short_theme_is_rejected_with_a_named_field(self, client):
        response = await client.post("/api/runs", json={"theme": "ab"})
        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "theme"

    async def test_streaming_emits_nodes_then_a_newsletter_then_done(self, client):
        run_id = await create_run(client)
        events = await drain_stream(client, run_id)

        assert events["node"], "expected node progress events"
        assert len(events["newsletter"]) == 1
        assert events["done"][-1]["status"] == "done"

    async def test_streaming_marks_the_run_finished_in_history(self, client):
        run_id = await create_run(client)
        await drain_stream(client, run_id)
        detail = (await client.get(f"/api/runs/{run_id}")).json()
        assert detail["status"] == "done"
        assert detail["newsletter"]["sections"]

    async def test_streaming_an_unknown_run_reports_not_found(self, client):
        events = await drain_stream(client, "does-not-exist")
        assert events["error"][0]["message"] == "Run not found"
        assert events["done"][0]["status"] == "not_found"


class TestHistory:
    async def test_runs_are_listed_newest_first(self, client):
        first = await create_run(client, theme="first theme here")
        second = await create_run(client, theme="second theme here")
        listed = (await client.get("/api/runs")).json()
        assert [row["run_id"] for row in listed][:2] == [second, first]

    async def test_history_rows_decode_their_config(self, client):
        await create_run(client)
        assert (await client.get("/api/runs")).json()[0]["config"]["theme"] == RUN_BODY["theme"]

    async def test_history_can_be_filtered_by_status(self, client):
        await create_run(client)
        assert (await client.get("/api/runs", params={"status": "done"})).json() == []

    async def test_limit_is_bounded(self, client):
        assert (await client.get("/api/runs", params={"limit": 0})).status_code == 422
        assert (await client.get("/api/runs", params={"limit": 500})).status_code == 422

    async def test_unknown_run_is_404(self, client):
        assert (await client.get("/api/runs/nope")).status_code == 404

    async def test_delete_removes_the_run(self, client):
        run_id = await create_run(client)
        assert (await client.delete(f"/api/runs/{run_id}")).status_code == 200
        assert (await client.get(f"/api/runs/{run_id}")).status_code == 404
        assert (await client.delete(f"/api/runs/{run_id}")).status_code == 404


class TestBookmarks:
    """Regression guard: this endpoint used to demand query parameters while the
    frontend sent a JSON body, so saving an article always failed with a 422."""

    BODY = {
        "article_id": "abc123",
        "url": "https://reuters.com/story",
        "title": "A story",
        "source_name": "Reuters",
    }

    async def test_a_json_body_is_accepted(self, client):
        run_id = await create_run(client)
        response = await client.post(f"/api/runs/{run_id}/bookmarks", json=self.BODY)
        assert response.status_code == 201, response.text
        assert response.json()["article_id"] == "abc123"

    async def test_saving_twice_does_not_duplicate(self, client):
        run_id = await create_run(client)
        await client.post(f"/api/runs/{run_id}/bookmarks", json=self.BODY)
        await client.post(f"/api/runs/{run_id}/bookmarks", json=self.BODY)
        assert len((await client.get(f"/api/runs/{run_id}/bookmarks")).json()) == 1

    async def test_bookmarks_can_be_removed(self, client):
        run_id = await create_run(client)
        await client.post(f"/api/runs/{run_id}/bookmarks", json=self.BODY)
        assert (await client.delete(f"/api/runs/{run_id}/bookmarks/abc123")).status_code == 200
        assert (await client.delete(f"/api/runs/{run_id}/bookmarks/abc123")).status_code == 404

    async def test_bookmarking_an_unknown_run_is_404(self, client):
        assert (await client.post("/api/runs/nope/bookmarks", json=self.BODY)).status_code == 404

    async def test_the_reading_list_spans_runs(self, client):
        for index in range(2):
            run_id = await create_run(client, theme=f"theme number {index}")
            await client.post(f"/api/runs/{run_id}/bookmarks", json=self.BODY)
        assert len((await client.get("/api/bookmarks")).json()) == 2

    async def test_missing_required_fields_are_reported(self, client):
        run_id = await create_run(client)
        response = await client.post(f"/api/runs/{run_id}/bookmarks", json={"url": "x"})
        assert response.status_code == 422
        assert {error["field"] for error in response.json()["errors"]} >= {"article_id", "title"}


class TestExport:
    async def test_markdown_and_html_download(self, client):
        run_id = await create_run(client)
        await drain_stream(client, run_id)

        markdown = await client.get(f"/api/runs/{run_id}/export/markdown")
        assert markdown.status_code == 200
        assert markdown.headers["content-type"].startswith("text/markdown")
        assert f"newsletter-{run_id}.md" in markdown.headers["content-disposition"]

        html = await client.get(f"/api/runs/{run_id}/export/html")
        assert html.status_code == 200
        assert html.text.startswith("<!doctype html>")

    async def test_exporting_before_the_run_finishes_is_a_conflict(self, client):
        run_id = await create_run(client)
        response = await client.get(f"/api/runs/{run_id}/export/markdown")
        assert response.status_code == 409

    async def test_unknown_format_is_rejected(self, client):
        run_id = await create_run(client)
        assert (await client.get(f"/api/runs/{run_id}/export/docx")).status_code == 400

    async def test_unknown_run_is_404(self, client):
        assert (await client.get("/api/runs/nope/export/markdown")).status_code == 404

    async def test_pdf_reports_501_when_the_renderer_is_absent(self, client):
        run_id = await create_run(client)
        await drain_stream(client, run_id)
        response = await client.get(f"/api/runs/{run_id}/export/pdf")
        assert response.status_code in (200, 501)
        if response.status_code == 501:
            assert "weasyprint" in response.json()["detail"].lower()


class TestTopology:
    async def test_topology_is_served_for_the_pipeline_view(self, client):
        body = (await client.get("/api/graph/topology")).json()
        assert {node["id"] for node in body["nodes"]} >= {"planner", "composer"}
        assert body["edges"]
