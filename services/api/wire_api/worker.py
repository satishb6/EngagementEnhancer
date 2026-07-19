"""Celery app: ingestion beat, corpus cycles, retention sweeps.

Trace context propagates through task headers, so a briefing generated from an
item fetched an hour ago shares a trace_id with that fetch.

NOTE: video generation has NO task here and never will. The only video code
path starts in a request handler behind an entitlement check — see
wire_api/generation/. This is a tested invariant, not a convention.
"""

import asyncio
from typing import Any

from celery import Celery, Task
from celery.schedules import crontab

from wire_api.logging import configure_logging, get_logger
from wire_api.settings import get_settings
from wire_api.tracing.context import TraceContext, clear_trace, set_trace

log = get_logger(__name__)

settings = get_settings()

celery_app = Celery(
    "wire",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        # staggered by offset minutes to avoid thundering herd
        "ingest-due-sources": {
            "task": "wire.ingest_due_sources",
            "schedule": 300.0,
        },
        "corpus-cycle": {
            "task": "wire.corpus_cycle",
            "schedule": 600.0,
        },
        "rank-all-users": {
            "task": "wire.rank_all_users",
            "schedule": crontab(minute="15", hour="*/2"),
        },
        "trace-retention": {
            "task": "wire.trace_retention",
            "schedule": crontab(minute="40", hour="3"),
        },
        "artifact-ttl-sweep": {
            "task": "wire.artifact_ttl_sweep",
            "schedule": crontab(minute="20", hour="4"),
        },
        "publish-due": {
            "task": "wire.publish_due",
            "schedule": 60.0,
        },
        "poll-video-jobs": {
            # polls PROGRESS of user-initiated video jobs; never creates one
            "task": "wire.poll_video_jobs",
            "schedule": 30.0,
        },
        "engagement-sync": {
            "task": "wire.engagement_sync",
            "schedule": crontab(minute="5", hour="*/6"),
        },
    },
)


class TracedTask(Task):  # type: ignore[type-arg]
    """Restores the caller's trace context from task headers."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        configure_logging()
        headers = getattr(self.request, "headers", None) or {}
        trace_headers = {
            k: v for k, v in headers.items() if isinstance(k, str) and k.startswith("wire_")
        }
        set_trace(TraceContext.from_headers(trace_headers))
        try:
            return super().__call__(*args, **kwargs)
        finally:
            clear_trace()


celery_app.Task = TracedTask


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


@celery_app.task(name="wire.ingest_due_sources", base=TracedTask)
def ingest_due_sources() -> dict[str, Any]:
    from wire_api.db import session_scope
    from wire_api.ingestion.runner import due_sources, ingest_source

    async def _run() -> dict[str, Any]:
        totals = {"sources": 0, "items_new": 0}
        async with session_scope() as session:
            for source in await due_sources(session):
                try:
                    metrics = await ingest_source(session, source)
                    totals["sources"] += 1
                    totals["items_new"] += int(metrics["items_new"])
                except Exception as exc:  # noqa: BLE001
                    log.error("ingest.source_failed", source=source.name, error=str(exc))
        return totals

    return run_async(_run())  # type: ignore[no-any-return]


@celery_app.task(name="wire.corpus_cycle", base=TracedTask)
def corpus_cycle() -> dict[str, int]:
    from wire_api.corpus.pipeline import run_corpus_cycle

    return run_async(run_corpus_cycle())  # type: ignore[no-any-return]


@celery_app.task(name="wire.rank_all_users", base=TracedTask)
def rank_all_users() -> dict[str, int]:
    from wire_api.ranking.service import rank_all_users as _rank

    return run_async(_rank())  # type: ignore[no-any-return]


@celery_app.task(name="wire.trace_retention", base=TracedTask)
def trace_retention() -> int:
    from wire_api.tracing.retention import strip_old_payloads

    return run_async(strip_old_payloads())  # type: ignore[no-any-return]


@celery_app.task(name="wire.artifact_ttl_sweep", base=TracedTask)
def artifact_ttl_sweep() -> int:
    from wire_api.generation.ttl import sweep_expired_artifacts

    return run_async(sweep_expired_artifacts())  # type: ignore[no-any-return]


@celery_app.task(name="wire.publish_due", base=TracedTask)
def publish_due() -> int:
    from wire_api.publishing.service import post_due_publications

    return run_async(post_due_publications())  # type: ignore[no-any-return]


@celery_app.task(name="wire.poll_video_jobs", base=TracedTask)
def poll_video_jobs() -> int:
    """Advances ALREADY-RUNNING video jobs (all user-initiated). Creates none."""
    from wire_api.generation.video import poll_running_video_jobs

    return run_async(poll_running_video_jobs())  # type: ignore[no-any-return]


@celery_app.task(name="wire.engagement_sync", base=TracedTask)
def engagement_sync() -> int:
    from wire_api.publishing.service import sync_engagement

    return run_async(sync_engagement())  # type: ignore[no-any-return]


@celery_app.task(name="wire.eager_generation", base=TracedTask)
def eager_generation(job_ids: list[str]) -> dict[str, Any]:
    """Runs EAGER-tier jobs (text/image/gif) created by the take endpoint.
    Job rows already exist with persisted cost estimates; this executes them."""
    from wire_api.generation.orchestrator import execute_jobs

    return run_async(execute_jobs(job_ids))  # type: ignore[no-any-return]
