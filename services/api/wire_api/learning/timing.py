"""Loop 4 — TIMING. Per-platform, per-weekday hourly engagement curve →
schedule suggestions."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import LearningEvent, TimingStat

# sensible cold-start defaults per platform (local time hours)
DEFAULT_SLOTS: dict[str, list[int]] = {
    "x": [8, 12, 18],
    "linkedin": [8, 10, 17],
    "instagram": [11, 19, 21],
    "threads": [9, 13, 20],
    "tiktok": [12, 19, 22],
    "facebook": [9, 13, 20],
    "youtube": [12, 17, 20],
}


async def record_publish_engagement(
    session: AsyncSession, user_id: uuid.UUID, platform: str,
    posted_at: datetime, engagement: float, trigger_id: uuid.UUID | None = None,
) -> None:
    weekday, hour = posted_at.weekday(), posted_at.hour
    stat = (
        await session.execute(
            select(TimingStat).where(
                TimingStat.user_id == user_id,
                TimingStat.platform == platform,
                TimingStat.weekday == weekday,
                TimingStat.hour == hour,
            )
        )
    ).scalar_one_or_none()
    if stat is None:
        stat = TimingStat(user_id=user_id, platform=platform, weekday=weekday, hour=hour)
        session.add(stat)
    stat.posts += 1
    stat.engagement_sum += engagement
    session.add(LearningEvent(
        user_id=user_id, loop="timing", trigger_kind="publish", trigger_id=trigger_id,
        detail={"platform": platform, "weekday": weekday, "hour": hour},
    ))


async def suggested_slots(
    session: AsyncSession, user_id: uuid.UUID, platform: str, weekday: int, n: int = 3
) -> list[int]:
    """Best posting hours for a platform+weekday: learned where there's data,
    defaults where there isn't. Cold start never degrades."""
    stats = (
        (
            await session.execute(
                select(TimingStat).where(
                    TimingStat.user_id == user_id,
                    TimingStat.platform == platform,
                    TimingStat.weekday == weekday,
                    TimingStat.posts >= 2,
                )
            )
        )
        .scalars()
        .all()
    )
    learned = sorted(
        stats, key=lambda s: (s.engagement_sum / s.posts) if s.posts else 0.0, reverse=True
    )
    hours = [s.hour for s in learned[:n]]
    for h in DEFAULT_SLOTS.get(platform, [9, 13, 19]):
        if len(hours) >= n:
            break
        if h not in hours:
            hours.append(h)
    return hours[:n]


async def reset_timing(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(TimingStat).where(TimingStat.user_id == user_id))
    session.add(LearningEvent(user_id=user_id, loop="timing", trigger_kind="reset", detail={}))
