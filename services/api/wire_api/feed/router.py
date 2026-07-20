"""The deck's data plane: feed, batched swipes, keeps, why-shown."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from wire_api.auth.deps import DB, CurrentEntitlement, CurrentUser
from wire_api.learning.taste import apply_swipe
from wire_api.models import (
    Briefing,
    FeedItem,
    LearningEvent,
    Swipe,
    SwipeDirection,
    Take,
)
from wire_api.models.base import utcnow, uuid7
from wire_api.ranking.service import rank_user

router = APIRouter(tags=["feed"])


def _briefing_json(b: Briefing) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "headline": b.headline,
        "body": b.body,
        "word_count": b.word_count,
        "confidence": b.confidence,
        "contested": b.contested,
        "source_links": b.source_links,
        "published_at": b.published_at.isoformat() if b.published_at else None,
        "cluster_id": str(b.cluster_id),
    }


@router.get("/feed")
async def get_feed(
    user: CurrentUser,
    ent: CurrentEntitlement,
    session: DB,
    cursor: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """Today's ranked deck with a stable cursor (rank_position) so the client
    can resume mid-deck."""
    feed_date = utcnow().strftime("%Y-%m-%d")
    rows = (
        await session.execute(
            select(FeedItem, Briefing)
            .join(Briefing, Briefing.id == FeedItem.briefing_id)
            .where(
                FeedItem.user_id == user.id,
                FeedItem.feed_date == feed_date,
                FeedItem.rank_position >= cursor,
                FeedItem.swiped_at.is_(None),
            )
            .order_by(FeedItem.rank_position)
            .limit(min(limit, ent.briefings_per_day))
        )
    ).all()

    if not rows and cursor == 0:
        # first open of the day: build the feed on demand rather than waiting
        # for the next beat tick
        await rank_user(session, user)
        await session.commit()
        rows = (
            await session.execute(
                select(FeedItem, Briefing)
                .join(Briefing, Briefing.id == FeedItem.briefing_id)
                .where(
                    FeedItem.user_id == user.id,
                    FeedItem.feed_date == feed_date,
                    FeedItem.swiped_at.is_(None),
                )
                .order_by(FeedItem.rank_position)
                .limit(min(limit, ent.briefings_per_day))
            )
        ).all()

    now = utcnow()
    items = []
    for feed_item, briefing in rows:
        if feed_item.served_at is None:
            feed_item.served_at = now
        items.append({
            "feed_item_id": str(feed_item.id),
            "position": feed_item.rank_position,
            "rank_score": feed_item.rank_score,
            "briefing": _briefing_json(briefing),
        })
    await session.commit()

    total_today = (
        await session.execute(
            select(FeedItem).where(
                FeedItem.user_id == user.id, FeedItem.feed_date == feed_date
            )
        )
    ).scalars()
    total = len(list(total_today))
    next_cursor = items[-1]["position"] + 1 if items else cursor
    return {"items": items, "next_cursor": next_cursor, "total_today": total}


class SwipeIn(BaseModel):
    feed_item_id: uuid.UUID
    direction: SwipeDirection
    dwell_ms: int = Field(ge=0, le=600_000, default=0)
    client_event_id: str = Field(min_length=8, max_length=64)


class SwipeBatch(BaseModel):
    swipes: list[SwipeIn] = Field(min_length=1, max_length=10)


@router.post("/swipe")
async def post_swipes(batch: SwipeBatch, user: CurrentUser, session: DB) -> dict[str, Any]:
    """Batched — a 50-card session is 10 requests, not 50. Idempotent on
    (feed_item_id, client_event_id): retries never double-count."""
    accepted = 0
    duplicates = 0
    for s in batch.swipes:
        feed_item = (
            await session.execute(
                select(FeedItem).where(
                    FeedItem.id == s.feed_item_id, FeedItem.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if feed_item is None:
            continue

        stmt = (
            pg_insert(Swipe)
            .values(
                id=uuid7(), user_id=user.id, feed_item_id=feed_item.id,
                direction=s.direction, dwell_ms=s.dwell_ms,
                client_event_id=s.client_event_id, swiped_at=utcnow(),
                created_at=utcnow(), updated_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["feed_item_id", "client_event_id"])
            .returning(Swipe.id)
        )
        inserted_id = (await session.execute(stmt)).scalar_one_or_none()
        if inserted_id is None:
            duplicates += 1
            continue

        feed_item.swiped_at = utcnow()
        accepted += 1

        briefing = (
            await session.execute(select(Briefing).where(Briefing.id == feed_item.briefing_id))
        ).scalar_one_or_none()
        if briefing is not None:
            await apply_swipe(session, user.id, briefing, s.direction, s.dwell_ms, inserted_id)

    await session.commit()
    return {"accepted": accepted, "duplicates": duplicates}


@router.post("/swipe/undo")
async def undo_last_swipe(user: CurrentUser, session: DB) -> dict[str, Any]:
    last = (
        await session.execute(
            select(Swipe)
            .where(Swipe.user_id == user.id, Swipe.undone.is_(False))
            .order_by(Swipe.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to undo.")
    last.undone = True
    feed_item = (
        await session.execute(select(FeedItem).where(FeedItem.id == last.feed_item_id))
    ).scalar_one_or_none()
    if feed_item is not None:
        feed_item.swiped_at = None
    await session.commit()
    return {"undone_feed_item_id": str(last.feed_item_id)}


@router.get("/session/keeps")
async def session_keeps(user: CurrentUser, session: DB) -> dict[str, Any]:
    """The right-swiped set for today, ordered for review."""
    feed_date = utcnow().strftime("%Y-%m-%d")
    rows = (
        await session.execute(
            select(Swipe, FeedItem, Briefing)
            .join(FeedItem, FeedItem.id == Swipe.feed_item_id)
            .join(Briefing, Briefing.id == FeedItem.briefing_id)
            .where(
                Swipe.user_id == user.id,
                Swipe.direction == SwipeDirection.RIGHT,
                Swipe.undone.is_(False),
                FeedItem.feed_date == feed_date,
            )
            .order_by(Swipe.created_at)
        )
    ).all()

    take_map = {
        t.briefing_id: t
        for t in (
            await session.execute(select(Take).where(Take.user_id == user.id))
        ).scalars()
    }
    keeps = []
    for swipe, feed_item, briefing in rows:
        take = take_map.get(briefing.id)
        keeps.append({
            "feed_item_id": str(feed_item.id),
            "briefing": _briefing_json(briefing),
            "take": {
                "id": str(take.id),
                "text": take.text_content,
                "stance": take.stance,
                "source": take.source.value,
            } if take else None,
        })
    return {"keeps": keeps, "count": len(keeps)}


@router.get("/feed/why/{feed_item_id}")
async def why_shown(feed_item_id: uuid.UUID, user: CurrentUser, session: DB) -> dict[str, Any]:
    """'Why am I being shown this' — a real answer from the learning log."""
    feed_item = (
        await session.execute(
            select(FeedItem).where(FeedItem.id == feed_item_id, FeedItem.user_id == user.id)
        )
    ).scalar_one_or_none()
    if feed_item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feed item not found.")
    recent = (
        (
            await session.execute(
                select(LearningEvent)
                .where(LearningEvent.user_id == user.id, LearningEvent.loop == "taste")
                .order_by(LearningEvent.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    right_regions: dict[str, int] = {}
    for ev in recent:
        if ev.detail.get("direction") == "right" and ev.detail.get("region"):
            r = str(ev.detail["region"])
            right_regions[r] = right_regions.get(r, 0) + 1
    return {
        "rank_score": feed_item.rank_score,
        "rank_position": feed_item.rank_position,
        "recent_kept_regions": right_regions,
        "explanation": (
            "Ranked by similarity to what you keep, your source protocols, "
            "and recency. Your recent keeps in "
            + (", ".join(sorted(right_regions)) if right_regions else "no region yet")
            + " shaped this."
        ),
    }
