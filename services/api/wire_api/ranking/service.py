"""Per-user feed ranking over the shared briefing pool.

Score = 0.45 · cosine(briefing, interest) + 0.25 · protocol source match
      + 0.20 · recency (half-life 8h)     + 0.10 · diversity
Then MMR re-rank, ≤3 briefings per domain per day, top N by tier.
"""

import math
import uuid
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.db import session_scope
from wire_api.logging import get_logger
from wire_api.models import (
    Briefing,
    Entitlement,
    FeedItem,
    ProtocolSource,
    Source,
    Tier,
    User,
    UserProtocol,
)
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.settings import get_settings
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

MMR_LAMBDA = 0.72


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


async def _protocol_domains(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = (
        await session.execute(
            select(Source.domain)
            .join(ProtocolSource, ProtocolSource.source_id == Source.id)
            .join(UserProtocol, UserProtocol.id == ProtocolSource.protocol_id)
            .where(UserProtocol.user_id == user_id)
        )
    ).scalars()
    return {d for d in rows if d}


async def rank_user(session: AsyncSession, user: User) -> int:
    """Build today's feed for one user. Pure CPU over the shared pool —
    zero model calls, which is the entire point."""
    settings = get_settings()
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one_or_none()
    feed_size = settings.feed_size_free if (ent is None or ent.tier is Tier.FREE) \
        else settings.feed_size_paid

    protocol = (
        await session.execute(
            select(UserProtocol)
            .where(UserProtocol.user_id == user.id, UserProtocol.is_default.is_(True))
        )
    ).scalar_one_or_none()
    interest = (
        np.asarray(protocol.interest_vector, dtype=np.float64)
        if protocol is not None and protocol.interest_vector is not None
        else None
    )
    region_weights: dict[str, float] = dict(protocol.region_weights) if protocol else {}
    domains = await _protocol_domains(session, user.id)

    briefings = (
        (
            await session.execute(
                select(Briefing)
                .where(Briefing.expired.is_(False), Briefing.embedding.is_not(None))
                .order_by(Briefing.published_at.desc())
                .limit(600)
            )
        )
        .scalars()
        .all()
    )
    if not briefings:
        return 0

    # already-swiped briefings never come back
    seen = set(
        (
            await session.execute(
                select(FeedItem.briefing_id).where(
                    FeedItem.user_id == user.id, FeedItem.swiped_at.is_not(None)
                )
            )
        ).scalars()
    )

    now = utcnow()
    scored: list[tuple[Briefing, float, np.ndarray]] = []
    for b in briefings:
        if b.id in seen:
            continue
        vec = np.asarray(b.embedding, dtype=np.float64)
        interest_score = _cosine(interest, vec) if interest is not None else 0.0

        source_score = 0.0
        for link in b.source_links or []:
            if link.get("domain") in domains:
                source_score = 1.0
                break

        age_h = max((now - (b.published_at or now)).total_seconds() / 3600.0, 0.0)
        recency = math.pow(0.5, age_h / settings.recency_half_life_hours)

        score = (
            settings.rank_w_interest * interest_score
            + settings.rank_w_source * source_score
            + settings.rank_w_recency * recency
        )
        # per-region taste weighting (loop 1 extension)
        region = await _briefing_region(session, b)
        if region and region in region_weights:
            score *= max(region_weights[region], 0.0)
        scored.append((b, score, vec))

    scored.sort(key=lambda t: t[1], reverse=True)

    # MMR: penalise similarity to already-picked items so one story doesn't
    # own the deck; then hard-cap per domain
    picked: list[tuple[Briefing, float]] = []
    picked_vecs: list[np.ndarray] = []
    domain_counts: dict[str, int] = {}
    for b, base_score, vec in scored:
        if len(picked) >= feed_size:
            break
        primary_domain = (b.source_links or [{}])[0].get("domain", "")
        if domain_counts.get(primary_domain, 0) >= settings.max_per_domain_per_day:
            continue
        redundancy = max((_cosine(vec, pv) for pv in picked_vecs), default=0.0)
        mmr = MMR_LAMBDA * base_score - (1 - MMR_LAMBDA) * redundancy
        # diversity term folds into the final ordering score
        final = mmr + settings.rank_w_diversity * (1.0 - redundancy)
        picked.append((b, final))
        picked_vecs.append(vec)
        if primary_domain:
            domain_counts[primary_domain] = domain_counts.get(primary_domain, 0) + 1

    picked.sort(key=lambda t: t[1], reverse=True)

    feed_date = now.strftime("%Y-%m-%d")
    # replace today's unserved items; served/swiped rows stay for history
    await session.execute(
        delete(FeedItem).where(
            FeedItem.user_id == user.id,
            FeedItem.feed_date == feed_date,
            FeedItem.served_at.is_(None),
        )
    )
    existing_today = set(
        (
            await session.execute(
                select(FeedItem.briefing_id).where(
                    FeedItem.user_id == user.id, FeedItem.feed_date == feed_date
                )
            )
        ).scalars()
    )
    position = 0
    added = 0
    for b, score in picked:
        if b.id in existing_today:
            continue
        session.add(FeedItem(
            user_id=user.id, briefing_id=b.id, rank_score=float(score),
            rank_position=position, feed_date=feed_date,
        ))
        position += 1
        added += 1
    await session.flush()
    return added


_region_cache: dict[uuid.UUID, str] = {}


async def _briefing_region(session: AsyncSession, briefing: Briefing) -> str:
    if briefing.id in _region_cache:
        return _region_cache[briefing.id]
    from wire_api.models import Cluster

    region = (
        await session.execute(
            select(Cluster.region_key).where(Cluster.id == briefing.cluster_id)
        )
    ).scalar_one_or_none() or ""
    _region_cache[briefing.id] = region
    return region


async def rank_all_users() -> dict[str, int]:
    async with session_scope() as session:
        users = (
            (await session.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        )
        total = 0
        for user in users:
            async with traced_span(
                session, Stage.RANK, entity_type="user", entity_id=str(user.id),
                user_id=user.id,
            ) as span:
                added = await rank_user(session, user)
                span.payload["count"] = added
                total += added
    return {"users": len(users), "feed_items": total}


def explain_scores(user_vec: Any, briefing_vec: Any) -> dict[str, float]:
    """Small helper the 'why am I seeing this' endpoint uses."""
    a = np.asarray(user_vec, dtype=np.float64)
    b = np.asarray(briefing_vec, dtype=np.float64)
    return {"interest_similarity": _cosine(a, b)}
