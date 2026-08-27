import pytest

pytestmark = pytest.mark.asyncio


async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_reports_version(client):
    assert response_version(await client.get("/api/health")) == "0.3.0"


def response_version(response) -> str:
    return response.json()["version"]


async def test_readiness_reports_each_dependency(client):
    body = (await client.get("/api/ready")).json()
    assert body["status"] in {"ready", "degraded"}
    assert set(body["checks"]) == {"database", "llm", "search", "scheduler"}
    assert body["checks"]["database"]["ok"] is True


async def test_status_flags_mock_data(client):
    body = (await client.get("/api/status")).json()
    assert body["llm_provider"] == "mock"
    assert body["search_providers"] == ["mock"]
    assert body["using_real_data"] is False


async def test_every_response_carries_a_request_id(client):
    response = await client.get("/api/health")
    assert response.headers["X-Request-ID"]


async def test_supplied_request_id_is_echoed(client):
    response = await client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
