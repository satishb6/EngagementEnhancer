"""Loop 1 — TASTE. Swipes, dwell, and source taps move the interest vector.

Asymmetric learning rates: dislike is weaker signal than like. Every update
is a logged LearningEvent so 'why am I being shown this' has a real answer.
"""

import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import (
    Briefing,
    Cluster,
    LearningEvent,
    SwipeDirection,
    UserProtocol,
)
from wire_api.settings import get_settings


def _normalise(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


async def apply_swipe(
    session: AsyncSession,
    user_id: uuid.UUID,
    briefing: Briefing,
    direction: SwipeDirection,
    dwell_ms: int,
    swipe_id: uuid.UUID,
) -> None:
    settings = get_settings()
    protocol = (
        await session.execute(
            select(UserProtocol).where(
                UserProtocol.user_id == user_id, UserProtocol.is_default.is_(True)
            )
        )
    ).scalar_one_or_none()
    if protocol is None or briefing.embedding is None:
        return

    b = np.asarray(briefing.embedding, dtype=np.float64)
    if protocol.interest_vector is None:
        current = np.zeros_like(b)
    else:
        current = np.asarray(protocol.interest_vector, dtype=np.float64)

    if direction is SwipeDirection.RIGHT:
        lr = settings.lr_swipe_right
        updated = current + lr * (b - current)
        detail = {"direction": "right", "lr": lr}
    else:
        lr = settings.lr_swipe_left
        updated = current - lr * b
        detail = {"direction": "left", "lr": lr}

    # dwell above threshold without a fast flick: small positive nudge
    if dwell_ms >= settings.dwell_threshold_ms:
        updated = updated + settings.lr_dwell * b
        detail["dwell_nudge"] = settings.lr_dwell

    protocol.interest_vector = list(_normalise(updated).astype(float))

    # per-region weights: like/dislike also tilts the region multiplier so a
    # user can like AI news but dislike AI-funding news
    region = (
        await session.execute(
            select(Cluster.region_key).where(Cluster.id == briefing.cluster_id)
        )
    ).scalar_one_or_none()
    if region:
        weights = dict(protocol.region_weights or {})
        w = weights.get(region, 1.0)
        w += 0.05 if direction is SwipeDirection.RIGHT else -0.03
        weights[region] = float(np.clip(w, 0.2, 2.0))
        protocol.region_weights = weights
        detail["region"] = region
        detail["region_weight"] = weights[region]

    session.add(LearningEvent(
        user_id=user_id, loop="taste", trigger_kind="swipe",
        trigger_id=swipe_id, detail=detail,
    ))


async def reset_taste(session: AsyncSession, user_id: uuid.UUID) -> None:
    protocol = (
        await session.execute(
            select(UserProtocol).where(
                UserProtocol.user_id == user_id, UserProtocol.is_default.is_(True)
            )
        )
    ).scalar_one_or_none()
    if protocol is not None:
        protocol.interest_vector = None
        protocol.region_weights = {}
        session.add(LearningEvent(
            user_id=user_id, loop="taste", trigger_kind="reset", detail={},
        ))
