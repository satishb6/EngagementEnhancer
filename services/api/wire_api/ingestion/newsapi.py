"""News API adapter — NewsData / GNews / Mediastack behind one interface.
The vendor is a settings flip, not a code change."""

from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from wire_api.ingestion.base import FetchedItem, FetchResult
from wire_api.models import Source
from wire_api.settings import get_settings


class NewsVendor(Protocol):
    async def fetch(self, client: httpx.AsyncClient, query: str, category: str) -> list[FetchedItem]: ...


def _domain(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class NewsDataVendor:
    async def fetch(self, client: httpx.AsyncClient, query: str, category: str) -> list[FetchedItem]:
        params: dict[str, Any] = {"apikey": get_settings().newsdata_api_key, "language": "en"}
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        resp = await client.get("https://newsdata.io/api/1/latest", params=params)
        resp.raise_for_status()
        return [
            FetchedItem(
                canonical_url=a.get("link", ""),
                title=(a.get("title") or "")[:500],
                body=(a.get("description") or a.get("content") or "")[:20000],
                domain=_domain(a.get("link", "")),
                author=", ".join(a.get("creator") or []) if a.get("creator") else "",
                published_at=_iso(a.get("pubDate")),
            )
            for a in resp.json().get("results", [])
            if a.get("link")
        ]


class GNewsVendor:
    async def fetch(self, client: httpx.AsyncClient, query: str, category: str) -> list[FetchedItem]:
        params: dict[str, Any] = {"apikey": get_settings().gnews_api_key, "lang": "en", "max": 25}
        endpoint = "top-headlines"
        if query:
            endpoint = "search"
            params["q"] = query
        if category:
            params["category"] = category
        resp = await client.get(f"https://gnews.io/api/v4/{endpoint}", params=params)
        resp.raise_for_status()
        return [
            FetchedItem(
                canonical_url=a.get("url", ""),
                title=(a.get("title") or "")[:500],
                body=(a.get("description") or a.get("content") or "")[:20000],
                domain=_domain(a.get("url", "")),
                published_at=_iso(a.get("publishedAt")),
            )
            for a in resp.json().get("articles", [])
            if a.get("url")
        ]


class MediastackVendor:
    async def fetch(self, client: httpx.AsyncClient, query: str, category: str) -> list[FetchedItem]:
        params: dict[str, Any] = {
            "access_key": get_settings().mediastack_api_key, "languages": "en", "limit": 25,
        }
        if query:
            params["keywords"] = query
        if category:
            params["categories"] = category
        resp = await client.get("http://api.mediastack.com/v1/news", params=params)
        resp.raise_for_status()
        return [
            FetchedItem(
                canonical_url=a.get("url", ""),
                title=(a.get("title") or "")[:500],
                body=(a.get("description") or "")[:20000],
                domain=_domain(a.get("url", "")),
                author=a.get("author") or "",
                published_at=_iso(a.get("published_at")),
            )
            for a in resp.json().get("data", [])
            if a.get("url")
        ]


_VENDORS: dict[str, NewsVendor] = {
    "newsdata": NewsDataVendor(),
    "gnews": GNewsVendor(),
    "mediastack": MediastackVendor(),
}


class NewsAPIAdapter:
    kind = "newsapi"

    async def fetch(self, source: Source) -> FetchResult:
        vendor = _VENDORS[get_settings().news_api_vendor]
        query = str(source.config.get("query", ""))
        category = str(source.config.get("category", ""))
        async with httpx.AsyncClient(timeout=30) as client:
            items = await vendor.fetch(client, query, category)
        return FetchResult(items=items, items_fetched=len(items))
