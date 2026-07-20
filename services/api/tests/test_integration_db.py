"""Integration tests against real Postgres (testcontainers or CI service).

Proves the four Phase-1 gates:
1. overlapping users share the SAME briefing rows
2. ledger balance is correct after mixed debits/refunds/resets
3. vector search returns correct order and uses the HNSW index
4. deleting a user leaves the shared corpus intact
"""

import numpy as np
import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_user_kwargs
from wire_api.billing.credits import (
    InsufficientCredits,
    balance,
    commit_reservation,
    grant,
    refund_reservation,
    reserve,
)
from wire_api.models import (
    EMBED_DIM,
    Briefing,
    Cluster,
    Entitlement,
    FeedItem,
    LedgerReason,
    Swipe,
    Take,
    Tier,
    User,
)
from wire_api.models.base import utcnow, uuid7

pytestmark = pytest.mark.integration

RNG = np.random.default_rng(3)


def _vec(seed_base: np.ndarray | None = None, noise: float = 0.05) -> list[float]:
    base = seed_base if seed_base is not None else RNG.normal(0, 1, EMBED_DIM)
    v = base + RNG.normal(0, noise, EMBED_DIM)
    return list((v / np.linalg.norm(v)).astype(float))


async def _mk_briefing(db: AsyncSession, center: np.ndarray | None = None) -> Briefing:
    cluster = Cluster(centroid=_vec(center), member_count=2,
                      first_seen_at=utcnow(), last_grown_at=utcnow())
    db.add(cluster)
    await db.flush()
    briefing = Briefing(
        cluster_id=cluster.id, headline="Test event occurs",
        body="Fifty words " * 10, word_count=50,
        embedding=_vec(center), published_at=utcnow(),
    )
    db.add(briefing)
    await db.flush()
    return briefing


async def test_users_share_briefing_rows(db: AsyncSession) -> None:
    briefings = [await _mk_briefing(db) for _ in range(5)]
    before = (await db.execute(select(func.count()).select_from(Briefing))).scalar_one()

    users = []
    for _ in range(3):
        u = User(**make_user_kwargs())
        db.add(u)
        await db.flush()
        users.append(u)
        for pos, b in enumerate(briefings):
            db.add(FeedItem(user_id=u.id, briefing_id=b.id, rank_position=pos,
                            feed_date="2026-07-19"))
    await db.flush()

    after = (await db.execute(select(func.count()).select_from(Briefing))).scalar_one()
    assert after == before, "briefing count grew with user count — shared-corpus violation"

    distinct_served = (
        await db.execute(select(func.count(func.distinct(FeedItem.briefing_id))))
    ).scalar_one()
    assert distinct_served == 5


async def test_ledger_balance_after_mixed_sequence(db: AsyncSession) -> None:
    u = User(**make_user_kwargs())
    db.add(u)
    await db.flush()

    await grant(db, u.id, 725, reason=LedgerReason.PERIOD_GRANT, idempotency_key="g1")
    job_a, job_b = uuid7(), uuid7()

    await reserve(db, u.id, 100, job_a)          # hold 100
    await commit_reservation(db, u.id, job_a, 100)  # release + debit 100
    await reserve(db, u.id, 100, job_b)          # hold 100
    await refund_reservation(db, u.id, job_b)    # failed → full refund
    await grant(db, u.id, 725, reason=LedgerReason.PERIOD_GRANT, idempotency_key="g2")
    await grant(db, u.id, 725, reason=LedgerReason.PERIOD_GRANT, idempotency_key="g2")  # dup

    assert await balance(db, u.id) == 725 - 100 + 725

    # settling twice is a no-op, not a double charge
    await commit_reservation(db, u.id, job_a, 100)
    assert await balance(db, u.id) == 1350


async def test_reserve_rejects_overdraw(db: AsyncSession) -> None:
    u = User(**make_user_kwargs())
    db.add(u)
    await db.flush()
    await grant(db, u.id, 50, idempotency_key="g")
    with pytest.raises(InsufficientCredits):
        await reserve(db, u.id, 100, uuid7())
    assert await balance(db, u.id) == 50


async def test_vector_search_order_and_hnsw_index(db: AsyncSession) -> None:
    center = RNG.normal(0, 1, EMBED_DIM)
    near = await _mk_briefing(db, center)
    for _ in range(10):
        await _mk_briefing(db, RNG.normal(0, 1, EMBED_DIM))
    await db.commit()

    query_vec = _vec(center, noise=0.01)
    rows = (
        await db.execute(
            select(Briefing.id)
            .order_by(Briefing.embedding.cosine_distance(query_vec))
            .limit(3)
        )
    ).scalars().all()
    assert rows[0] == near.id, "nearest briefing not returned first"

    # the HNSW index must actually be used
    await db.execute(text("SET enable_seqscan = off"))
    explain = (
        await db.execute(
            text(
                "EXPLAIN SELECT id FROM briefing ORDER BY embedding <=> "
                f"'{query_vec}'::vector LIMIT 3"
            )
        )
    ).scalars().all()
    plan = "\n".join(explain)
    assert "ix_briefing_embedding_hnsw" in plan, plan


async def test_user_deletion_leaves_corpus_intact(db: AsyncSession) -> None:
    briefing = await _mk_briefing(db)
    u = User(**make_user_kwargs())
    db.add(u)
    await db.flush()
    db.add(Entitlement(user_id=u.id, tier=Tier.FREE))
    fi = FeedItem(user_id=u.id, briefing_id=briefing.id, rank_position=0,
                  feed_date="2026-07-19")
    db.add(fi)
    await db.flush()
    db.add(Swipe(user_id=u.id, feed_item_id=fi.id, direction="right",
                 client_event_id="e" * 12))
    db.add(Take(user_id=u.id, briefing_id=briefing.id, text_content="mine"))
    await db.flush()

    # user-owned rows cascade; financial rows RESTRICT (delete those first)
    await db.execute(delete(Entitlement).where(Entitlement.user_id == u.id))
    await db.execute(delete(User).where(User.id == u.id))
    await db.flush()

    assert (await db.execute(select(func.count()).select_from(Briefing))).scalar_one() >= 1
    assert (await db.execute(select(func.count()).select_from(Cluster))).scalar_one() >= 1
    remaining_feed = (
        await db.execute(select(func.count()).select_from(FeedItem))
    ).scalar_one()
    assert remaining_feed == 0, "per-user rows should cascade away"


async def test_briefing_count_independent_of_user_count(db: AsyncSession) -> None:
    """Add 100 users; corpus row counts must not move."""
    for _ in range(5):
        await _mk_briefing(db)
    briefings_before = (
        await db.execute(select(func.count()).select_from(Briefing))
    ).scalar_one()
    clusters_before = (
        await db.execute(select(func.count()).select_from(Cluster))
    ).scalar_one()

    for i in range(100):
        db.add(User(**make_user_kwargs(f"bulk{i}@wire.test")))
    await db.flush()

    assert (
        await db.execute(select(func.count()).select_from(Briefing))
    ).scalar_one() == briefings_before
    assert (
        await db.execute(select(func.count()).select_from(Cluster))
    ).scalar_one() == clusters_before
