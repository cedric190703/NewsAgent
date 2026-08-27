"""Schedule endpoints. The create route previously mixed body and query
parameters, so the documented payload could not actually be posted."""

import pytest

pytestmark = pytest.mark.asyncio

SCHEDULE_BODY = {
    "themes": ["ocean restoration", "coral reefs"],
    "cron_expr": "0 9 * * mon-fri",
    "config": {"theme": "ocean restoration", "max_sources": 5, "providers": ["mock"]},
}


async def create_schedule(client, **overrides) -> dict:
    response = await client.post("/api/schedules", json={**SCHEDULE_BODY, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    async def test_a_single_json_body_is_accepted(self, client):
        body = await create_schedule(client)
        assert body["themes"] == SCHEDULE_BODY["themes"]
        assert body["cron_expr"] == SCHEDULE_BODY["cron_expr"]
        assert body["enabled"] is True

    async def test_the_next_firing_time_is_returned(self, client):
        assert await create_schedule(client) is not None
        body = await create_schedule(client, cron_expr="0 9 * * *")
        assert body["next_run_at"].endswith("09:00:00+00:00")

    @pytest.mark.parametrize("expression", ["nope", "* * * *", "99 * * * *", ""])
    async def test_invalid_cron_is_rejected_at_the_edge(self, client, expression):
        response = await client.post(
            "/api/schedules", json={**SCHEDULE_BODY, "cron_expr": expression}
        )
        assert response.status_code == 422
        assert "cron" in response.text.lower()

    async def test_blank_themes_are_dropped(self, client):
        body = await create_schedule(client, themes=["  ", "reefs", ""])
        assert body["themes"] == ["reefs"]

    async def test_an_invalid_run_config_is_rejected(self, client):
        response = await client.post(
            "/api/schedules", json={**SCHEDULE_BODY, "config": {"theme": "x"}}
        )
        assert response.status_code == 422


class TestManage:
    async def test_schedules_are_listed(self, client):
        await create_schedule(client)
        assert len((await client.get("/api/schedules")).json()) == 1

    async def test_toggling_uses_a_json_body(self, client):
        schedule_id = (await create_schedule(client))["schedule_id"]
        response = await client.patch(
            f"/api/schedules/{schedule_id}", json={"enabled": False}
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    async def test_toggling_an_unknown_schedule_is_404(self, client):
        assert (await client.patch("/api/schedules/nope", json={"enabled": True})).status_code == 404

    async def test_delete_removes_the_schedule(self, client):
        schedule_id = (await create_schedule(client))["schedule_id"]
        assert (await client.delete(f"/api/schedules/{schedule_id}")).status_code == 200
        assert (await client.delete(f"/api/schedules/{schedule_id}")).status_code == 404

    async def test_running_a_schedule_now_creates_a_run(self, client):
        schedule_id = (await create_schedule(client))["schedule_id"]
        response = await client.post(f"/api/schedules/{schedule_id}/run")
        assert response.status_code == 200
        assert response.json()["status"] == "started"

    async def test_running_an_unknown_schedule_is_404(self, client):
        assert (await client.post("/api/schedules/nope/run")).status_code == 404
