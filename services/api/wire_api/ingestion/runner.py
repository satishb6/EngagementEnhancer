"""Ingestion runner: adapter dispatch, content-hash dedup, trace emission,
adaptive poll intervals."""

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.ingestion.base import FetchResult, SourceAdapter
from wire_api.ingestion.newsapi import NewsAPIAdapter
from wire_api.ingestion.reddit import RedditAdapter
from wire_api.ingestion.rss import RSSAdapter
from wire_api.ingestion.web import WebAdapter
from wire_api.ingestion.youtube import YouTubeAdapter, YouTubeQuota
from wire_api.logging import get_logger
from wire_api.models import RawItem, Source, SourceKind
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.tracing.emit import get_redis
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

# adaptive interval bounds
MIN_INTERVAL_S = 300
MAX_INTERVAL_S = 6 * 3600


def build_adapters() -> dict[SourceKind, SourceAdapter]:
    return {
        SourceKind.RSS: RSSAdapter(),
        SourceKind.REDDIT: RedditAdapter(),
        SourceKind.YOUTUBE: YouTubeAdapter(YouTubeQuota(get_redis())),
        SourceKind.NEWSAPI: NewsAPIAdapter(),
        SourceKind.WEB: WebAdapter(),
    }


async def ingest_source(session: AsyncSession, source: Source) -> dict[str, Any]:
    """Fetch one source, dedup, insert. Returns run metrics."""
    adapter = build_adapters()[source.kind]
    async with traced_span(
        session, Stage.FETCH, entity_type="source", entity_id=str(source.id)
    ) as span:
        t0 = time.perf_counter()
        result: FetchResult = await adapter.fetch(source)

        new_count = 0
        if result.items:
            hashes = [item.content_hash for item in result.items]
            existing = set(
                (
                    await session.execute(
                        select(RawItem.content_hash).where(RawItem.content_hash.in_(hashes))
                    )
                ).scalars()
            )
            seen_this_batch: set[str] = set()
            for item in result.items:
                h = item.content_hash
                if h in existing or h in seen_this_batch:
                    continue
                seen_this_batch.add(h)
                session.add(RawItem(
                    source_id=source.id,
                    canonical_url=item.canonical_url,
                    title=item.title,
                    body=item.body,
                    author=item.author,
                    domain=item.domain or source.domain,
                    published_at=item.published_at,
                    fetched_at=utcnow(),
                    content_hash=h,
                    meta=item.meta,
                ))
                new_count += 1

        # adaptive interval: quiet sources back off, active ones speed up
        if new_count == 0:
            source.consecutive_empty_polls += 1
            if source.consecutive_empty_polls >= 3:
                source.poll_interval_s = min(source.poll_interval_s * 2, MAX_INTERVAL_S)
        else:
            source.consecutive_empty_polls = 0
            source.poll_interval_s = max(source.poll_interval_s // 2, MIN_INTERVAL_S)
        source.last_polled_at_epoch = time.time()
        if result.etag:
            source.etag = result.etag
        if result.last_modified:
            source.last_modified = result.last_modified

        metrics = {
            "source": source.name,
            "kind": source.kind.value,
            "http_status": result.http_status,
            "items_fetched": result.items_fetched,
            "items_new": new_count,
            "quota_consumed": result.quota_consumed,
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
        span.payload.update(metrics)
        log.info("ingest.run", **metrics)
        return metrics


async def due_sources(session: AsyncSession) -> list[Source]:
    now = time.time()
    sources = (
        (await session.execute(select(Source).where(Source.is_active.is_(True)))).scalars().all()
    )
    return [s for s in sources if now - s.last_polled_at_epoch >= s.poll_interval_s]
