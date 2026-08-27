import asyncio

from app.core.cache import TTLCache


async def test_hit_and_miss():
    cache: TTLCache[str] = TTLCache(ttl_seconds=60)
    assert cache.get("k") is None
    cache.set("k", "v")
    assert cache.get("k") == "v"


async def test_entries_expire():
    cache: TTLCache[str] = TTLCache(ttl_seconds=0.01)
    cache.set("k", "v")
    await asyncio.sleep(0.05)
    assert cache.get("k") is None


async def test_get_or_load_runs_the_loader_once():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    calls = 0

    async def loader() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await cache.get_or_load("k", loader) == 42
    assert await cache.get_or_load("k", loader) == 42
    assert calls == 1


async def test_concurrent_callers_share_one_load():
    """The stampede this exists to prevent: N research branches, one fetch."""

    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    calls = 0

    async def slow_loader() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return 7

    results = await asyncio.gather(
        *(cache.get_or_load("same-key", slow_loader) for _ in range(10))
    )
    assert results == [7] * 10
    assert calls == 1


async def test_loader_failure_propagates_and_is_not_cached():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    attempts = 0

    async def flaky() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("boom")
        return 5

    try:
        await cache.get_or_load("k", flaky)
    except ValueError:
        pass
    else:
        raise AssertionError("expected the loader error to propagate")

    assert await cache.get_or_load("k", flaky) == 5
    assert attempts == 2


async def test_max_entries_is_enforced():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60, max_entries=3)
    for index in range(6):
        cache.set(f"k{index}", index)
    assert len(cache._values) <= 3


async def test_clear_empties_the_cache():
    cache: TTLCache[int] = TTLCache(ttl_seconds=60)
    cache.set("k", 1)
    cache.clear()
    assert cache.get("k") is None
