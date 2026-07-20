"""Loop 3 — FORMAT. (topic_region × content_type × platform) → success rate,
Bayesian-smoothed so early data doesn't overfit."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import FormatStat, LearningEvent

# Beta prior: ~3 pseudo-observations at a 30% success rate
PRIOR_ALPHA = 1.0
PRIOR_BETA = 2.3


def smoothed_success(stat: FormatStat | None) -> float:
    if stat is None:
        return PRIOR_ALPHA / (PRIOR_ALPHA + PRIOR_BETA)
    return (stat.picks + PRIOR_ALPHA) / (stat.impressions + PRIOR_ALPHA + PRIOR_BETA)


async def _get_or_create(
    session: AsyncSession, user_id: uuid.UUID, region: str, content_type: str, platform: str
) -> FormatStat:
    stat = (
        await session.execute(
            select(FormatStat).where(
                FormatStat.user_id == user_id,
                FormatStat.region_key == region,
                FormatStat.content_type == content_type,
                FormatStat.platform == platform,
            )
        )
    ).scalar_one_or_none()
    if stat is None:
        stat = FormatStat(user_id=user_id, region_key=region,
                          content_type=content_type, platform=platform)
        session.add(stat)
        await session.flush()
    return stat


async def record_impression(
    session: AsyncSession, user_id: uuid.UUID, region: str, content_type: str, platform: str
) -> None:
    stat = await _get_or_create(session, user_id, region, content_type, platform)
    stat.impressions += 1


async def record_pick(
    session: AsyncSession, user_id: uuid.UUID, region: str, content_type: str,
    platform: str, trigger_id: uuid.UUID | None = None,
) -> None:
    stat = await _get_or_create(session, user_id, region, content_type, platform)
    stat.picks += 1
    session.add(LearningEvent(
        user_id=user_id, loop="format", trigger_kind="pick", trigger_id=trigger_id,
        detail={"region": region, "content_type": content_type, "platform": platform,
                "success": round(smoothed_success(stat), 3)},
    ))


async def record_engagement(
    session: AsyncSession, user_id: uuid.UUID, region: str, content_type: str,
    platform: str, engagement: float,
) -> None:
    stat = await _get_or_create(session, user_id, region, content_type, platform)
    stat.engagement_sum += engagement


async def variant_bias(
    session: AsyncSession, user_id: uuid.UUID, region: str, platform: str
) -> dict[str, float]:
    """Per-content-type success for this user/region/platform. The contact
    sheet orders and weights variants with this."""
    stats = (
        (
            await session.execute(
                select(FormatStat).where(
                    FormatStat.user_id == user_id,
                    FormatStat.region_key == region,
                    FormatStat.platform == platform,
                )
            )
        )
        .scalars()
        .all()
    )
    return {s.content_type: smoothed_success(s) for s in stats}


async def reset_format(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(FormatStat).where(FormatStat.user_id == user_id))
    session.add(LearningEvent(user_id=user_id, loop="format", trigger_kind="reset", detail={}))
