"""Reddit adapter — app-only OAuth, per-subreddit, respectful of rate limits."""

from datetime import UTC, datetime

import httpx

from wire_api.ingestion.base import FetchedItem, FetchResult
from wire_api.models import Source
from wire_api.settings import get_settings

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

_token_cache: dict[str, str] = {}


async def _get_token(client: httpx.AsyncClient) -> str:
    if "token" in _token_cache:
        return _token_cache["token"]
    s = get_settings()
    resp = await client.post(
        TOKEN_URL,
        auth=(s.reddit_client_id, s.reddit_client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": s.reddit_user_agent},
    )
    resp.raise_for_status()
    token = str(resp.json()["access_token"])
    _token_cache["token"] = token
    return token


class RedditAdapter:
    kind = "reddit"

    async def fetch(self, source: Source) -> FetchResult:
        s = get_settings()
        subreddit = str(source.config.get("subreddit", ""))
        listing = str(source.config.get("listing", "hot"))
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _get_token(client)
            resp = await client.get(
                f"https://oauth.reddit.com/r/{subreddit}/{listing}",
                params={"limit": 50},
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": s.reddit_user_agent,
                },
            )
            if resp.status_code == 401:
                _token_cache.clear()  # token expired; next run re-auths
            resp.raise_for_status()

        items: list[FetchedItem] = []
        for child in resp.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18"):
                continue
            url = f"https://www.reddit.com{post.get('permalink', '')}"
            items.append(
                FetchedItem(
                    canonical_url=post.get("url_overridden_by_dest") or url,
                    title=post.get("title", "")[:500],
                    body=post.get("selftext", "")[:20000],
                    domain=post.get("domain", "reddit.com"),
                    author=post.get("author", ""),
                    published_at=datetime.fromtimestamp(post.get("created_utc", 0), tz=UTC),
                    meta={"score": post.get("score", 0), "subreddit": subreddit,
                          "num_comments": post.get("num_comments", 0)},
                )
            )
        return FetchResult(items=items, items_fetched=len(items), http_status=resp.status_code)
