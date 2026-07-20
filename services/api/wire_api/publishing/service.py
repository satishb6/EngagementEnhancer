"""Publishing service: scheduling, per-account rate limits, retry with
backoff, dead-letter, engagement sync feeding loops 3 & 4."""

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.billing.credits import ContentPrice, commit_reservation, reserve
from wire_api.db import session_scope
from wire_api.learning.format_loop import record_engagement
from wire_api.learning.timing import record_publish_engagement, suggested_slots
from wire_api.logging import get_logger
from wire_api.models import (
    Artifact,
    Briefing,
    Cluster,
    Entitlement,
    GenerationJob,
    Publication,
    PublicationStatus,
    SocialAccount,
    Take,
    Tier,
)
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.providers.byok import decrypt_key, encrypt_key
from wire_api.publishing.provider import PublishRequest, get_publish_provider
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

MAX_ATTEMPTS = 3
HARD_DAILY_CAP = 8  # posts per account per day — anti-flagging ceiling


class RateLimited(RuntimeError):
    pass


async def posts_today(session: AsyncSession, account: SocialAccount) -> int:
    since = utcnow() - timedelta(hours=24)
    count = (
        await session.execute(
            select(func.count()).select_from(Publication).where(
                Publication.social_account_id == account.id,
                Publication.posted_at >= since,
                Publication.status == PublicationStatus.POSTED,
            )
        )
    ).scalar_one()
    return int(count)


async def schedule_publication(
    session: AsyncSession,
    user_id: object,
    artifact: Artifact,
    account: SocialAccount,
    scheduled_for: datetime | None,
) -> Publication:
    """Create a scheduled publication. Enforces the anti-flagging ceiling and
    charges publish credits (pro tier) with reserve-then-commit."""
    used = await posts_today(session, account)
    ceiling = min(account.daily_post_ceiling, HARD_DAILY_CAP)
    if used >= ceiling:
        raise RateLimited(
            f"{account.platform.value} account is at its {ceiling}-post daily ceiling. "
            "This protects the account from platform spam detection."
        )

    if scheduled_for is None:
        now = utcnow()
        hours = await suggested_slots(
            session, account.user_id, account.platform.value, now.weekday()
        )
        base = now.replace(minute=0, second=0, microsecond=0)
        candidates = [base.replace(hour=h) for h in hours if h > now.hour]
        scheduled_for = candidates[0] if candidates else now + timedelta(minutes=10)
        # jitter: exact intervals look like a bot because they are one
        scheduled_for += timedelta(minutes=random.randint(1, 17))

    pub = Publication(
        user_id=account.user_id,
        artifact_id=artifact.id,
        social_account_id=account.id,
        status=PublicationStatus.SCHEDULED,
        scheduled_for=scheduled_for,
    )
    session.add(pub)
    await session.flush()

    ent = (
        await session.execute(
            select(Entitlement).where(Entitlement.user_id == account.user_id)
        )
    ).scalar_one()
    if ent.tier is Tier.PRO:
        await reserve(session, account.user_id, int(ContentPrice.PUBLISH), pub.id)
    return pub


async def post_due_publications() -> int:
    """Beat task: post everything whose time has come."""
    posted = 0
    async with session_scope() as session:
        due = (
            (
                await session.execute(
                    select(Publication).where(
                        Publication.status == PublicationStatus.SCHEDULED,
                        Publication.scheduled_for <= utcnow(),
                    ).limit(50)
                )
            )
            .scalars()
            .all()
        )
        for pub in due:
            await _post_one(session, pub)
            posted += 1
    return posted


async def _post_one(session: AsyncSession, pub: Publication) -> None:
    account = (
        await session.execute(
            select(SocialAccount).where(SocialAccount.id == pub.social_account_id)
        )
    ).scalar_one()
    artifact = (
        await session.execute(select(Artifact).where(Artifact.id == pub.artifact_id))
    ).scalar_one()

    provider = get_publish_provider()
    pub.status = PublicationStatus.POSTING
    pub.attempt_count += 1

    media = [artifact.storage_uri] if artifact.storage_uri else []
    text = artifact.text_content
    if not text:
        # media-only artifacts still carry the take's words
        job = (
            await session.execute(
                select(GenerationJob).where(GenerationJob.id == artifact.job_id)
            )
        ).scalar_one_or_none()
        if job and job.take_id:
            take = (
                await session.execute(select(Take).where(Take.id == job.take_id))
            ).scalar_one_or_none()
            text = take.text_content if take else ""

    async with traced_span(
        session, Stage.PUBLISH, entity_type="publication",
        entity_id=str(pub.id), user_id=pub.user_id,
    ) as span:
        result = await provider.publish(PublishRequest(
            platform=account.platform.value,
            text=text,
            media_urls=media,
            profile_key=decrypt_key(account.encrypted_token) if account.encrypted_token else "",
        ))
        span.payload.update({
            "platform": account.platform.value, "vendor": provider.vendor,
            "ok": result.ok, "cost_cents": 10.0 if result.ok else 0.0,
        })

    if result.ok:
        pub.status = PublicationStatus.POSTED
        pub.posted_at = utcnow()
        pub.external_post_id = result.external_post_id
        ent = (
            await session.execute(
                select(Entitlement).where(Entitlement.user_id == pub.user_id)
            )
        ).scalar_one()
        if ent.tier is Tier.PRO:
            await commit_reservation(session, pub.user_id, pub.id, int(ContentPrice.PUBLISH))
    else:
        pub.error = {"message": result.error, "attempt": pub.attempt_count}
        if pub.attempt_count >= MAX_ATTEMPTS:
            pub.status = PublicationStatus.DEAD_LETTER
            log.error("publish.dead_letter", publication=str(pub.id), error=result.error)
        else:
            # backoff: 2^attempt minutes
            pub.status = PublicationStatus.SCHEDULED
            pub.scheduled_for = utcnow() + timedelta(minutes=2 ** pub.attempt_count)


async def sync_engagement() -> int:
    """Harvest engagement for recent posts — feeds loops 3 (format) & 4 (timing)."""
    synced = 0
    provider = get_publish_provider()
    async with session_scope() as session:
        recent = (
            (
                await session.execute(
                    select(Publication).where(
                        Publication.status == PublicationStatus.POSTED,
                        Publication.posted_at >= utcnow() - timedelta(days=7),
                        Publication.external_post_id != "",
                    ).limit(100)
                )
            )
            .scalars()
            .all()
        )
        for pub in recent:
            account = (
                await session.execute(
                    select(SocialAccount).where(SocialAccount.id == pub.social_account_id)
                )
            ).scalar_one()
            data = await provider.get_engagement(pub.external_post_id, account.platform.value)
            if not data:
                continue
            pub.engagement = data
            pub.engagement_synced_at = utcnow()
            score = _engagement_score(data)

            artifact = (
                await session.execute(select(Artifact).where(Artifact.id == pub.artifact_id))
            ).scalar_one()
            job = (
                await session.execute(
                    select(GenerationJob).where(GenerationJob.id == artifact.job_id)
                )
            ).scalar_one_or_none()
            region = ""
            if job and job.take_id:
                take = (
                    await session.execute(select(Take).where(Take.id == job.take_id))
                ).scalar_one_or_none()
                if take:
                    region = (
                        await session.execute(
                            select(Cluster.region_key)
                            .join(Briefing, Briefing.cluster_id == Cluster.id)
                            .where(Briefing.id == take.briefing_id)
                        )
                    ).scalar_one_or_none() or ""
            await record_engagement(
                session, pub.user_id, region, artifact.content_type.value,
                account.platform.value, score,
            )
            if pub.posted_at:
                await record_publish_engagement(
                    session, pub.user_id, account.platform.value,
                    pub.posted_at, score, trigger_id=pub.id,
                )
            synced += 1
    return synced


def _engagement_score(data: dict[str, object]) -> float:
    flat: dict[str, float] = {}

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    flat[str(k).lower()] = float(v)
                else:
                    walk(v)

    walk(data)
    return (
        flat.get("likecount", flat.get("likes", 0.0))
        + 3.0 * flat.get("commentscount", flat.get("comments", 0.0))
        + 5.0 * flat.get("sharecount", flat.get("shares", flat.get("retweetcount", 0.0)))
        + 0.01 * flat.get("impressioncount", flat.get("impressions", 0.0))
    )


__all__ = [
    "HARD_DAILY_CAP",
    "RateLimited",
    "encrypt_key",
    "post_due_publications",
    "schedule_publication",
    "sync_engagement",
]
