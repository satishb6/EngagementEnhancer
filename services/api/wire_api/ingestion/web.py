"""Generic web adapter — readability extraction, robots.txt respected."""

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from wire_api.ingestion.base import FetchedItem, FetchResult
from wire_api.logging import get_logger
from wire_api.models import Source

log = get_logger(__name__)

UA = "wire/0.1 (+news aggregation; respects robots.txt)"

_robots_cache: dict[str, RobotFileParser] = {}


async def _allowed(client: httpx.AsyncClient, url: str) -> bool:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    parser = _robots_cache.get(origin)
    if parser is None:
        parser = RobotFileParser()
        try:
            resp = await client.get(f"{origin}/robots.txt", timeout=10)
            parser.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except httpx.HTTPError:
            parser.parse([])
        _robots_cache[origin] = parser
    return parser.can_fetch(UA, url)


def _extract(html: str) -> tuple[str, str]:
    """(title, body) via readability, falling back to soup text."""
    try:
        from readability import Document

        doc = Document(html)
        soup = BeautifulSoup(doc.summary(), "html.parser")
        return doc.short_title(), soup.get_text(separator="\n", strip=True)
    except Exception:  # noqa: BLE001 — readability chokes on odd markup; degrade
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        return title, soup.get_text(separator="\n", strip=True)[:20000]


class WebAdapter:
    kind = "web"

    async def fetch(self, source: Source) -> FetchResult:
        urls: list[str] = [str(u) for u in source.config.get("urls", [])]
        items: list[FetchedItem] = []
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers={"User-Agent": UA}
        ) as client:
            for url in urls[:20]:
                if not await _allowed(client, url):
                    log.info("web.robots_disallowed", url=url)
                    continue
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("web.fetch_failed", url=url, error=str(exc))
                    continue
                title, body = await asyncio.to_thread(_extract, resp.text)
                items.append(
                    FetchedItem(
                        canonical_url=str(resp.url),
                        title=title[:500],
                        body=body[:20000],
                        domain=urlparse(str(resp.url)).netloc.removeprefix("www."),
                    )
                )
        return FetchResult(items=items, items_fetched=len(items))
