"""Event bus + counters with two backends.

Redis when REDIS_URL is set (multi-process: separate workers still reach the
Wire Room). In-memory when it isn't (lite mode: API + embedded worker share
one process, so a local fanout and a dict are exactly right).
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from wire_api.settings import get_settings

CHANNEL = "wire:events"


class Bus(Protocol):
    async def publish(self, payload: str) -> None: ...

    def subscribe(self) -> "AsyncIterator[str]": ...


class InMemoryBus:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()

    async def publish(self, payload: str) -> None:
        for q in list(self._queues):
            if q.qsize() < 1000:
                q.put_nowait(payload)

    @asynccontextmanager
    async def listen(self) -> AsyncIterator[asyncio.Queue[str]]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._queues.add(q)
        try:
            yield q
        finally:
            self._queues.discard(q)


class RedisBus:
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def publish(self, payload: str) -> None:
        await self._redis.publish(CHANNEL, payload)

    @asynccontextmanager
    async def listen(self) -> AsyncIterator[asyncio.Queue[str]]:
        q: asyncio.Queue[str] = asyncio.Queue()
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)

        async def pump() -> None:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is not None:
                    q.put_nowait(str(msg["data"]))

        task = asyncio.create_task(pump())
        try:
            yield q
        finally:
            task.cancel()
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()


_bus: InMemoryBus | RedisBus | None = None


def get_bus() -> InMemoryBus | RedisBus:
    global _bus
    if _bus is None:
        url = get_settings().redis_url
        if url:
            try:
                _bus = RedisBus(url)
            except Exception:  # noqa: BLE001 — no redis client / bad url → lite mode
                _bus = InMemoryBus()
        else:
            _bus = InMemoryBus()
    return _bus


class Counters:
    """Daily quota counters: Redis INCRBY when available, dict otherwise."""

    def __init__(self) -> None:
        self._mem: dict[str, tuple[int, float]] = {}
        self._redis = None
        url = get_settings().redis_url
        if url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(url, decode_responses=True)
            except Exception:  # noqa: BLE001
                self._redis = None

    async def get(self, key: str) -> int:
        if self._redis is not None:
            try:
                return int(await self._redis.get(key) or 0)
            except Exception:  # noqa: BLE001 — fall through to memory
                pass
        value, expires = self._mem.get(key, (0, 0.0))
        return value if expires > time.time() else 0

    async def incr(self, key: str, amount: int, ttl_s: int = 93600) -> int:
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incrby(key, amount)
                pipe.expire(key, ttl_s)
                results = await pipe.execute()
                return int(results[0])
            except Exception:  # noqa: BLE001
                pass
        value, expires = self._mem.get(key, (0, 0.0))
        if expires <= time.time():
            value = 0
        value += amount
        self._mem[key] = (value, time.time() + ttl_s)
        return value


_counters: Counters | None = None


def get_counters() -> Counters:
    global _counters
    if _counters is None:
        _counters = Counters()
    return _counters
