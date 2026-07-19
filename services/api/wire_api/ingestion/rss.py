"""RSS/Atom adapter. feedparser handles the malformed feeds the real world
serves; etag/last-modified keep unchanged feeds free."""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser
import httpx

from wire_api.ingestion.base import FetchedItem, FetchResult
from wire_api.models import Source


def _entry_time(entry: feedparser.FeedParserDict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=UTC)
    return None


class RSSAdapter:
    kind = "rss"

    async def fetch(self, source: Source) -> FetchResult:
        url = str(source.config.get("url", ""))
        headers: dict[str, str] = {"User-Agent": "wire/0.1 (+news aggregation; respects robots)"}
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 304:
            return FetchResult(items=[], items_fetched=0, http_status=304, not_modified=True,
                               etag=source.etag, last_modified=source.last_modified)
        resp.raise_for_status()

        # feedparser is sync + CPU-ish; keep the event loop clean
        parsed = await asyncio.to_thread(feedparser.parse, resp.content)

        items: list[FetchedItem] = []
        for entry in parsed.entries[:100]:
            link = entry.get("link", "")
            if not link:
                continue
            body = ""
            if entry.get("content"):
                body = entry.content[0].get("value", "")
            body = body or entry.get("summary", "")
            items.append(
                FetchedItem(
                    canonical_url=link,
                    title=entry.get("title", "")[:500],
                    body=body[:20000],
                    domain=urlparse(link).netloc.removeprefix("www."),
                    author=entry.get("author", ""),
                    published_at=_entry_time(entry),
                )
            )
        return FetchResult(
            items=items,
            items_fetched=len(items),
            http_status=resp.status_code,
            etag=resp.headers.get("etag", ""),
            last_modified=resp.headers.get("last-modified", ""),
        )
