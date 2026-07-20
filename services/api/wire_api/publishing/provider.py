"""PublishProvider — the swappable unified-social-API boundary.

Per-profile pricing on these vendors is the dominant cost at scale; you WILL
want to switch. Nothing outside this module knows which vendor is live.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from wire_api.settings import get_settings


@dataclass
class PublishRequest:
    platform: str
    text: str
    media_urls: list[str] = field(default_factory=list)
    profile_key: str = ""  # vendor-side account handle/key (decrypted)
    schedule_iso: str | None = None


@dataclass
class PublishResult:
    ok: bool
    external_post_id: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkResult:
    """Account-linking handoff: the vendor hosts the OAuth dance."""

    url: str
    profile_key: str = ""


@runtime_checkable
class PublishProvider(Protocol):
    vendor: str

    async def link_account_url(self, user_ref: str) -> LinkResult: ...

    async def publish(self, request: PublishRequest) -> PublishResult: ...

    async def get_engagement(self, external_post_id: str, platform: str) -> dict[str, Any]: ...


class AyrshareProvider:
    vendor = "ayrshare"
    _base = "https://api.ayrshare.com/api"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self, profile_key: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if profile_key:
            headers["Profile-Key"] = profile_key
        return headers

    async def link_account_url(self, user_ref: str) -> LinkResult:
        async with httpx.AsyncClient(timeout=30) as client:
            # create (or fetch) a vendor profile for this user, then a JWT link URL
            profile_resp = await client.post(
                f"{self._base}/profiles",
                json={"title": user_ref},
                headers=self._headers(),
            )
            profile_resp.raise_for_status()
            profile_key = str(profile_resp.json().get("profileKey", ""))
            jwt_resp = await client.post(
                f"{self._base}/profiles/generateJWT",
                json={"profileKey": profile_key},
                headers=self._headers(),
            )
            jwt_resp.raise_for_status()
            return LinkResult(url=str(jwt_resp.json().get("url", "")), profile_key=profile_key)

    async def publish(self, request: PublishRequest) -> PublishResult:
        body: dict[str, Any] = {
            "post": request.text,
            "platforms": [request.platform],
        }
        if request.media_urls:
            body["mediaUrls"] = request.media_urls
        if request.schedule_iso:
            body["scheduleDate"] = request.schedule_iso
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base}/post", json=body, headers=self._headers(request.profile_key)
            )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code >= 400 or data.get("status") == "error":
            return PublishResult(ok=False, error=str(data or resp.text)[:500], raw=data)
        post_ids = data.get("postIds", [])
        external = str(post_ids[0].get("id", "")) if post_ids else str(data.get("id", ""))
        return PublishResult(ok=True, external_post_id=external, raw=data)

    async def get_engagement(self, external_post_id: str, platform: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/analytics/post",
                json={"id": external_post_id, "platforms": [platform]},
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                return {}
            return dict(resp.json())


class NullPublishProvider:
    """Dev fallback: records the intent, posts nothing, succeeds honestly."""

    vendor = "null"

    async def link_account_url(self, user_ref: str) -> LinkResult:
        return LinkResult(url="https://example.invalid/link-not-configured", profile_key="dev")

    async def publish(self, request: PublishRequest) -> PublishResult:
        return PublishResult(ok=True, external_post_id="dev-null-post",
                             raw={"note": "PUBLISH_VENDOR not configured; dry run"})

    async def get_engagement(self, external_post_id: str, platform: str) -> dict[str, Any]:
        return {}


def get_publish_provider() -> PublishProvider:
    settings = get_settings()
    if settings.publish_vendor == "ayrshare" and settings.ayrshare_api_key:
        return AyrshareProvider(settings.ayrshare_api_key)
    return NullPublishProvider()
