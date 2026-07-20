"""The lazy-generation rule, in code.

EAGER      auto on take submission: text ×N, image ×N, gif (ffmpeg, $0)
ON_DEMAND  explicit user action + entitlement: short video
GATED      explicit action + cost confirmation: long video

There is NO code path to a VIDEO job that isn't user-initiated. The gate
below is called by every executor, and tests/test_cost_guardrails.py greps
the codebase to prove video providers are reachable only via request
handlers. Get this wrong and the business doesn't work.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import (
    ContentType,
    Entitlement,
    GenerationJob,
    GenerationTier,
    Take,
    Tier,
    User,
)
from wire_api.models.base import utcnow


class TierViolation(RuntimeError):
    """A job tried to run outside its tier's rules. This is a bug or an
    attack, never a user error — log loudly."""


TIER_BY_CONTENT_TYPE: dict[ContentType, GenerationTier] = {
    ContentType.TEXT: GenerationTier.EAGER,
    ContentType.IMAGE: GenerationTier.EAGER,
    ContentType.GIF: GenerationTier.EAGER,
    ContentType.VIDEO_SHORT: GenerationTier.ON_DEMAND,
    ContentType.VIDEO_LONG: GenerationTier.GATED,
}

VIDEO_TYPES = {ContentType.VIDEO_SHORT, ContentType.VIDEO_LONG}


def assert_tier_allowed(job: GenerationJob, entitlement: Entitlement) -> None:
    """The single gate every generation job passes through before running."""
    expected_tier = TIER_BY_CONTENT_TYPE[job.content_type]
    if job.tier != expected_tier:
        raise TierViolation(
            f"job {job.id}: content_type {job.content_type} must run in tier "
            f"{expected_tier}, got {job.tier}"
        )

    if job.content_type in VIDEO_TYPES:
        if not job.user_initiated:
            raise TierViolation(
                f"job {job.id}: video job without user_initiated=True. "
                "There is no legal code path here."
            )
        if not entitlement.can_video:
            raise TierViolation(
                f"job {job.id}: tier '{entitlement.tier}' has no video entitlement."
            )

    if entitlement.tier is Tier.FREE and job.variant_index >= entitlement.variant_count:
        raise TierViolation(
            f"job {job.id}: free tier is capped at {entitlement.variant_count} variant(s)."
        )


async def selections_today(session: AsyncSession, user: User) -> int:
    """A 'selection' = a take that triggered generation, today."""
    since = utcnow() - timedelta(hours=24)
    count = (
        await session.execute(
            select(func.count(func.distinct(GenerationJob.take_id))).where(
                GenerationJob.user_id == user.id,
                GenerationJob.created_at >= since,
                GenerationJob.take_id.is_not(None),
            )
        )
    ).scalar_one()
    return int(count)


class SelectionCapExceeded(RuntimeError):
    def __init__(self, cap: int) -> None:
        self.cap = cap
        super().__init__(
            f"Daily selection cap reached ({cap}). Upgrading raises it — "
            "or come back tomorrow."
        )


async def assert_selection_allowed(
    session: AsyncSession, user: User, entitlement: Entitlement, take: Take
) -> None:
    """Server-side daily selection cap. Hostile clients hit this, not the UI."""
    existing_for_take = (
        await session.execute(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.take_id == take.id
            )
        )
    ).scalar_one()
    if existing_for_take:
        return  # regenerating an existing selection doesn't consume a new slot
    used = await selections_today(session, user)
    if used >= entitlement.selections_per_day:
        raise SelectionCapExceeded(entitlement.selections_per_day)


def artifact_ttl(entitlement: Entitlement) -> timedelta:
    """Free 48h, paid 30d, then cold storage."""
    return timedelta(hours=48) if entitlement.tier is Tier.FREE else timedelta(days=30)
