"""A small async TTL cache with single-flight semantics.

The graph fans out one research branch per sub-topic, and every branch asks the
RSS provider for the same feeds. Without this, an 8-feed / 4-subtopic run makes
32 identical HTTP requests instead of 8 — and single-flight matters because the
branches run *concurrently*, so plain expiry checking would still stampede.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, max_entries: int = 512) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._values: dict[str, tuple[float, T]] = {}
        self._inflight: dict[str, asyncio.Future[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if len(self._values) >= self._max_entries:
            self._evict_expired()
        if len(self._values) >= self._max_entries:
            oldest = min(self._values, key=lambda k: self._values[k][0])
            self._values.pop(oldest, None)
        self._values[key] = (time.monotonic() + self._ttl, value)

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, or run `loader` exactly once for concurrent callers."""

        cached = self.get(key)
        if cached is not None:
            return cached

        inflight = self._inflight.get(key)
        if inflight is not None:
            return await asyncio.shield(inflight)

        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await loader()
        except BaseException as exc:
            self._inflight.pop(key, None)
            if not future.done():
                future.set_exception(exc)
            # Nobody may be awaiting the future; keep the loop quiet about it.
            future.exception()
            raise
        else:
            self.set(key, value)
            self._inflight.pop(key, None)
            if not future.done():
                future.set_result(value)
            return value

    def clear(self) -> None:
        self._values.clear()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._values.items() if exp < now]:
            self._values.pop(key, None)
