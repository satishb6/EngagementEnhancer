"""YouTube Data API adapter.

CRITICAL: quota units tracked in Redis against the 10,000/day project cap.
search.list costs 100 units; playlistItems.list costs 1 — so channels are
fetched via their uploads playlist, never via search. At 80% consumption the
adapter refuses to run and logs loudly, instead of surprising you with a 403
at 100%.
"""

from datetime import UTC, datetime

import httpx
import redis.asyncio as aioredis

from wire_api.ingestion.base import FetchedItem, FetchResult
from wire_api.logging import get_logger
from wire_api.models import Source
from wire_api.settings import get_settings

log = get_logger(__name__)

BASE = "https://www.googleapis.com/youtube/v3"

COST_PLAYLIST_ITEMS = 1
COST_SEARCH = 100
COST_CHANNELS = 1

QUOTA_KEY_FMT = "wire:youtube:quota:{date}"
REFUSE_AT = 0.80


class YouTubeQuotaExceeded(RuntimeError):
    pass


class YouTubeQuota:
    """Redis-backed daily unit counter, shared across all workers."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    def _key(self) -> str:
        return QUOTA_KEY_FMT.format(date=datetime.now(UTC).strftime("%Y-%m-%d"))

    async def consumed(self) -> int:
        value = await self._redis.get(self._key())
        return int(value or 0)

    async def charge(self, units: int) -> int:
        """Charge units, or raise if the budget doesn't allow it."""
        cap = get_settings().youtube_daily_quota_units
        used = await self.consumed()
        if used + units > cap * REFUSE_AT:
            log.error(
                "youtube.quota_refused",
                used=used, requested=units, cap=cap,
                message="refusing at 80% of daily quota — raise the cap or wait for reset",
            )
            raise YouTubeQuotaExceeded(
                f"YouTube quota at {used}/{cap} units; refusing a {units}-unit call at the "
                f"{int(REFUSE_AT * 100)}% safety line."
            )
        pipe = self._redis.pipeline()
        pipe.incrby(self._key(), units)
        pipe.expire(self._key(), 60 * 60 * 26)
        results = await pipe.execute()
        return int(results[0])


class YouTubeAdapter:
    kind = "youtube"

    def __init__(self, quota: YouTubeQuota) -> None:
        self._quota = quota

    async def _uploads_playlist_id(self, client: httpx.AsyncClient, channel_id: str) -> str:
        await self._quota.charge(COST_CHANNELS)
        resp = await client.get(
            f"{BASE}/channels",
            params={"part": "contentDetails", "id": channel_id,
                    "key": get_settings().youtube_api_key},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return ""
        return str(items[0]["contentDetails"]["relatedPlaylists"]["uploads"])

    async def fetch(self, source: Source) -> FetchResult:
        cfg = source.config
        playlist_id = str(cfg.get("playlist_id", ""))
        quota_used = 0

        async with httpx.AsyncClient(timeout=30) as client:
            if not playlist_id and cfg.get("channel_id"):
                playlist_id = await self._uploads_playlist_id(client, str(cfg["channel_id"]))
                quota_used += COST_CHANNELS

            if not playlist_id:
                # search is the 100-unit path — only if config demands it
                query = str(cfg.get("query", ""))
                if not query:
                    return FetchResult(items=[], items_fetched=0)
                await self._quota.charge(COST_SEARCH)
                quota_used += COST_SEARCH
                resp = await client.get(
                    f"{BASE}/search",
                    params={"part": "snippet", "q": query, "type": "video",
                            "order": "date", "maxResults": 25,
                            "key": get_settings().youtube_api_key},
                )
                resp.raise_for_status()
                entries = resp.json().get("items", [])
                items = [self._item_from_search(e) for e in entries]
                return FetchResult(items=items, items_fetched=len(items),
                                   quota_consumed=quota_used, http_status=resp.status_code)

            await self._quota.charge(COST_PLAYLIST_ITEMS)
            quota_used += COST_PLAYLIST_ITEMS
            resp = await client.get(
                f"{BASE}/playlistItems",
                params={"part": "snippet", "playlistId": playlist_id, "maxResults": 25,
                        "key": get_settings().youtube_api_key},
            )
            resp.raise_for_status()

        items = [self._item_from_playlist(e) for e in resp.json().get("items", [])]
        return FetchResult(items=items, items_fetched=len(items),
                           quota_consumed=quota_used, http_status=resp.status_code)

    @staticmethod
    def _item_from_playlist(entry: dict) -> FetchedItem:  # type: ignore[type-arg]
        snippet = entry.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId", "")
        return FetchedItem(
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet.get("title", "")[:500],
            body=snippet.get("description", "")[:20000],
            domain="youtube.com",
            author=snippet.get("videoOwnerChannelTitle", ""),
            published_at=_parse_ts(snippet.get("publishedAt")),
            meta={"video_id": video_id},
        )

    @staticmethod
    def _item_from_search(entry: dict) -> FetchedItem:  # type: ignore[type-arg]
        snippet = entry.get("snippet", {})
        video_id = entry.get("id", {}).get("videoId", "")
        return FetchedItem(
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet.get("title", "")[:500],
            body=snippet.get("description", "")[:20000],
            domain="youtube.com",
            author=snippet.get("channelTitle", ""),
            published_at=_parse_ts(snippet.get("publishedAt")),
            meta={"video_id": video_id},
        )


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
