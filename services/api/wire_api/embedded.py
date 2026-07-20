"""Embedded worker — lite mode's replacement for Celery + beat.

All the beat-scheduled loops run as asyncio tasks inside the API process.
One process, zero infrastructure: right for local dev and a free Hugging
Face Space. The docker-compose scale path sets EMBEDDED_WORKER=0 and runs
the Celery worker instead — same task functions, different scheduler.

Video jobs are only ever POLLED here, never created (the lazy-generation
rule holds in every mode).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from wire_api.logging import get_logger

log = get_logger(__name__)


async def _ingest_due() -> Any:
    from wire_api.db import session_scope
    from wire_api.ingestion.runner import due_sources, ingest_source

    async with session_scope() as session:
        for source in await due_sources(session):
            try:
                await ingest_source(session, source)
            except Exception as exc:  # noqa: BLE001
                log.warning("embedded.ingest_failed", source=source.name, error=str(exc))


async def _corpus() -> Any:
    from wire_api.corpus.pipeline import run_corpus_cycle

    return await run_corpus_cycle()


async def _rank() -> Any:
    from wire_api.ranking.service import rank_all_users

    return await rank_all_users()


async def _publish() -> Any:
    from wire_api.publishing.service import post_due_publications

    return await post_due_publications()


async def _poll_video() -> Any:
    from wire_api.generation.video import poll_running_video_jobs

    return await poll_running_video_jobs()


async def _retention() -> Any:
    from wire_api.tracing.retention import strip_old_payloads

    return await strip_old_payloads()


async def _ttl() -> Any:
    from wire_api.generation.ttl import sweep_expired_artifacts

    return await sweep_expired_artifacts()


async def _engagement() -> Any:
    from wire_api.publishing.service import sync_engagement

    return await sync_engagement()


LOOPS: list[tuple[str, float, Callable[[], Awaitable[Any]]]] = [
    ("ingest", 300, _ingest_due),
    ("corpus", 600, _corpus),
    ("rank", 7200, _rank),
    ("publish", 60, _publish),
    ("video-poll", 30, _poll_video),
    ("retention", 86400, _retention),
    ("ttl-sweep", 86400, _ttl),
    ("engagement", 21600, _engagement),
]


def start_embedded_loops() -> list[asyncio.Task[None]]:
    async def runner(name: str, interval: float, fn: Callable[[], Awaitable[Any]]) -> None:
        # stagger startup so eight loops don't fire at once
        await asyncio.sleep(min(interval, 20) * (hash(name) % 5 + 1) / 5)
        while True:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a loop must never die
                log.warning("embedded.loop_error", loop=name, error=str(exc))
            await asyncio.sleep(interval)

    tasks = [
        asyncio.create_task(runner(name, interval, fn), name=f"wire-embedded-{name}")
        for name, interval, fn in LOOPS
    ]
    log.info("embedded.started", loops=[name for name, _i, _f in LOOPS])
    return tasks


def dispatch_generation(job_ids: list[str]) -> None:
    """Run eager generation jobs: in-process task in lite mode, Celery
    otherwise. Called by the take endpoint after commit."""
    from wire_api.settings import get_settings

    if get_settings().redis_url and not get_settings().embedded_worker:
        from wire_api.worker import eager_generation

        eager_generation.apply_async(args=[job_ids], headers={})
        return

    from wire_api.generation.orchestrator import execute_jobs

    async def _run() -> None:
        try:
            await execute_jobs(job_ids)
        except Exception as exc:  # noqa: BLE001
            log.warning("embedded.generation_failed", error=str(exc))

    asyncio.get_running_loop().create_task(_run())
