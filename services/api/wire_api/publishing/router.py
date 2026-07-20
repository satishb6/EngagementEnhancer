"""Publishing endpoints. Free tier gets 402 + a clipboard export — publishing
is the paywall, and it's an honest one (vendors bill per connected profile)."""

import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from wire_api.auth.deps import DB, CurrentEntitlement, CurrentUser
from wire_api.learning.timing import suggested_slots
from wire_api.models import (
    Artifact,
    Platform,
    Publication,
    PublicationStatus,
    SocialAccount,
)
from wire_api.models.base import utcnow
from wire_api.providers.byok import encrypt_key
from wire_api.publishing.provider import get_publish_provider
from wire_api.publishing.service import RateLimited, schedule_publication
from wire_api.settings import get_settings

router = APIRouter(prefix="/publish", tags=["publishing"])

UPGRADE_MESSAGE = (
    "Publishing posts for you is a paid feature — connected profiles cost the "
    "platform real money per month. Free tier copies content to your clipboard "
    "instead. Upgrading turns on scheduled auto-posting."
)


def _require_publishing(ent: Any) -> None:
    if not ent.can_publish:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, UPGRADE_MESSAGE)


@router.get("/accounts")
async def list_accounts(user: CurrentUser, session: DB) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(SocialAccount).where(
                    SocialAccount.user_id == user.id, SocialAccount.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(r.id), "platform": r.platform.value, "handle": r.handle,
         "connected_at": r.connected_at.isoformat() if r.connected_at else None,
         "daily_post_ceiling": r.daily_post_ceiling}
        for r in rows
    ]


@router.post("/accounts/link")
async def link_account(user: CurrentUser, ent: CurrentEntitlement, session: DB) -> dict[str, str]:
    """Returns the vendor-hosted OAuth URL. Tokens land encrypted via webhook
    or the /accounts/confirm call — never through the browser client."""
    _require_publishing(ent)
    provider = get_publish_provider()
    link = await provider.link_account_url(str(user.id))
    return {"url": link.url, "profile_key_set": str(bool(link.profile_key))}


class ConfirmAccountIn(BaseModel):
    platform: Platform
    handle: str = ""
    external_id: str = ""
    profile_key: str  # vendor profile key returned by the link flow


@router.post("/accounts/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_account(
    body: ConfirmAccountIn, user: CurrentUser, ent: CurrentEntitlement, session: DB
) -> dict[str, str]:
    _require_publishing(ent)
    account = SocialAccount(
        user_id=user.id, platform=body.platform, handle=body.handle,
        external_id=body.external_id or body.handle,
        encrypted_token=encrypt_key(body.profile_key),
        connected_at=utcnow(),
    )
    session.add(account)
    await session.commit()
    return {"account_id": str(account.id), "platform": body.platform.value}


class ScheduleIn(BaseModel):
    artifact_id: uuid.UUID
    account_id: uuid.UUID
    scheduled_for: datetime | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def schedule_post(
    body: ScheduleIn, user: CurrentUser, ent: CurrentEntitlement, session: DB
) -> dict[str, Any]:
    _require_publishing(ent)
    artifact = (
        await session.execute(
            select(Artifact).where(Artifact.id == body.artifact_id, Artifact.user_id == user.id)
        )
    ).scalar_one_or_none()
    account = (
        await session.execute(
            select(SocialAccount).where(
                SocialAccount.id == body.account_id, SocialAccount.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if artifact is None or account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact or account not found.")
    try:
        pub = await schedule_publication(session, user.id, artifact, account, body.scheduled_for)
        await session.commit()
    except RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    return {
        "publication_id": str(pub.id),
        "scheduled_for": pub.scheduled_for.isoformat() if pub.scheduled_for else None,
        "status": pub.status.value,
    }


@router.get("/queue")
async def publication_queue(user: CurrentUser, session: DB) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(Publication)
                .where(Publication.user_id == user.id)
                .order_by(Publication.scheduled_for.desc().nulls_last())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return [
        {"id": str(p.id), "status": p.status.value,
         "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
         "posted_at": p.posted_at.isoformat() if p.posted_at else None,
         "external_post_id": p.external_post_id,
         "engagement": p.engagement, "error": p.error}
        for p in rows
    ]


@router.get("/slots")
async def best_slots(
    user: CurrentUser, session: DB, platform: str = "x", weekday: int | None = None
) -> dict[str, Any]:
    day = weekday if weekday is not None else utcnow().weekday()
    hours = await suggested_slots(session, user.id, platform, day)
    return {"platform": platform, "weekday": day, "hours": hours}


@router.get("/clipboard/{artifact_id}")
async def clipboard_export(
    artifact_id: uuid.UUID, user: CurrentUser, session: DB, platform: str = "x"
) -> dict[str, Any]:
    """The free-tier path: content formatted for manual posting. One honest
    line about what upgrading changes. No nagging, no modal."""
    artifact = (
        await session.execute(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id)
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    return {
        "platform": platform,
        "text": artifact.text_content,
        "media_uri": artifact.storage_uri,
        "note": "Copied for manual posting. Pro posts and schedules this for you.",
    }


@router.post("/webhook")
async def publish_webhook(request: Request, session: DB) -> dict[str, str]:
    """Vendor status callbacks, signature-verified."""
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("x-wire-signature", "")
    expected = hmac.new(
        settings.publish_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not settings.publish_webhook_secret or not hmac.compare_digest(signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad webhook signature.")

    import orjson

    data = orjson.loads(body or b"{}")
    external_id = str(data.get("id", ""))
    new_status = str(data.get("status", ""))
    if external_id and new_status in ("success", "error"):
        pub = (
            await session.execute(
                select(Publication).where(Publication.external_post_id == external_id)
            )
        ).scalar_one_or_none()
        if pub is not None:
            pub.status = (
                PublicationStatus.POSTED if new_status == "success"
                else PublicationStatus.FAILED
            )
            await session.commit()
    return {"status": "ok"}
