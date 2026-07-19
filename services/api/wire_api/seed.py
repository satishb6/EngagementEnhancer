"""Seed a realistic dev dataset: 3 users, 200 raw items, ~60 clusters,
~60 briefings. Deterministic (seeded RNG) so runs are reproducible.

Run: uv run python -m wire_api.seed
"""

import asyncio
import hashlib
import random
from datetime import timedelta

import numpy as np
from sqlalchemy import func, select

from wire_api.auth.security import hash_password
from wire_api.db import session_scope
from wire_api.logging import configure_logging, get_logger
from wire_api.models import (
    EMBED_DIM,
    Briefing,
    Cluster,
    ClusterMember,
    Entitlement,
    FeedItem,
    ProtocolSource,
    RawItem,
    Source,
    SourceKind,
    Tier,
    User,
    UserProtocol,
    utcnow,
)

log = get_logger(__name__)

RNG = np.random.default_rng(42)
PYRNG = random.Random(42)

TOPICS: list[tuple[str, list[str]]] = [
    ("ai-policy", ["EU AI Act enforcement begins", "US states drift on AI rules",
                   "Model evaluations become mandatory", "Compute thresholds debated"]),
    ("semiconductors", ["TSMC expands Arizona fab", "HBM supply stays tight",
                        "China export controls widen", "RISC-V server push"]),
    ("climate-tech", ["Grid storage costs fall", "Fusion startup hits milestone",
                      "Carbon removal market doubles", "Heat pump adoption jumps"]),
    ("space", ["Starship reaches orbit again", "Lunar lander slips to Q3",
               "Satellite internet price war", "Debris rules tighten"]),
    ("biotech", ["CRISPR therapy approved", "AI protein design scales",
                 "Obesity drug supply strained", "mRNA flu vaccine trial"]),
    ("markets", ["Fed holds rates steady", "Chip stocks lead rally",
                 "IPO window reopens", "Credit spreads narrow"]),
]

DOMAINS = ["reuters.com", "apnews.com", "theverge.com", "arstechnica.com",
           "ft.com", "bloomberg.com", "wired.com", "nature.com"]

FILLER = (
    "Officials confirmed the change on Thursday. Analysts said the move was "
    "expected but the timing was not. Further detail is expected within days. "
    "The announcement follows months of speculation across the industry."
)


def unit_vector(base: np.ndarray, noise: float) -> list[float]:
    v = base + RNG.normal(0, noise, EMBED_DIM)
    return list((v / np.linalg.norm(v)).astype(float))


async def seed() -> None:
    async with session_scope() as s:
        existing = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        if existing:
            log.info("seed.skip", reason="users already exist", count=existing)
            return

        # -- users ------------------------------------------------------------
        users: list[User] = []
        for i, (email, tier) in enumerate(
            [("free@wire.dev", Tier.FREE), ("pro@wire.dev", Tier.PRO), ("byok@wire.dev", Tier.BYOK)]
        ):
            u = User(email=email, password_hash=hash_password("wire-dev-password"),
                     display_name=f"Dev User {i + 1}")
            s.add(u)
            await s.flush()
            s.add(Entitlement(
                user_id=u.id, tier=tier,
                briefings_per_day=20 if tier is Tier.FREE else 50,
                selections_per_day=3 if tier is Tier.FREE else 999,
                variant_count=1 if tier is Tier.FREE else 3,
                can_publish=tier is not Tier.FREE,
                can_video=tier is not Tier.FREE,
            ))
            users.append(u)

        # -- sources ----------------------------------------------------------
        sources: list[Source] = []
        for domain in DOMAINS:
            src = Source(kind=SourceKind.RSS, name=domain, domain=domain,
                         config={"url": f"https://{domain}/rss"})
            s.add(src)
            sources.append(src)
        await s.flush()

        # protocols: overlapping source sets so users share briefings
        for u in users:
            proto = UserProtocol(user_id=u.id, name="Default wire", is_default=True)
            s.add(proto)
            await s.flush()
            for src in PYRNG.sample(sources, 5):
                s.add(ProtocolSource(protocol_id=proto.id, source_id=src.id))

        # -- corpus: 6 topics × ~10 clusters × ~3-4 items = ~200 raw items ----
        topic_bases = {key: RNG.normal(0, 1, EMBED_DIM) for key, _ in TOPICS}
        n_items = 0
        n_clusters = 0
        now = utcnow()

        for topic_key, headlines in TOPICS:
            base = topic_bases[topic_key]
            for ci in range(10):
                cluster_center = base + RNG.normal(0, 0.35, EMBED_DIM)
                cluster_center = cluster_center / np.linalg.norm(cluster_center)
                headline = PYRNG.choice(headlines)
                cluster = Cluster(
                    centroid=list(cluster_center.astype(float)),
                    first_seen_at=now - timedelta(hours=PYRNG.uniform(1, 40)),
                    last_grown_at=now - timedelta(hours=PYRNG.uniform(0, 12)),
                    region_key=topic_key,
                )
                s.add(cluster)
                await s.flush()
                n_clusters += 1

                members = PYRNG.randint(2, 5)
                links = []
                for mi in range(members):
                    domain = PYRNG.choice(DOMAINS)
                    url = f"https://{domain}/{topic_key}/{ci}-{mi}"
                    body = f"{headline}. {FILLER}"
                    item = RawItem(
                        source_id=PYRNG.choice(sources).id,
                        canonical_url=url,
                        title=f"{headline} — report {mi + 1}",
                        body=body,
                        domain=domain,
                        published_at=now - timedelta(hours=PYRNG.uniform(1, 36)),
                        fetched_at=now,
                        content_hash=hashlib.sha256(url.encode()).hexdigest(),
                        embedding=unit_vector(cluster_center, 0.05),
                        embedded_at=now,
                        clustered_at=now,
                    )
                    s.add(item)
                    await s.flush()
                    sim = float(np.dot(np.array(item.embedding), cluster_center))
                    s.add(ClusterMember(cluster_id=cluster.id, raw_item_id=item.id,
                                        similarity=sim))
                    links.append({"url": url, "domain": domain, "title": item.title})
                    n_items += 1

                cluster.member_count = members
                cluster.briefed_member_count = members

                word_target = PYRNG.randint(50, 60)
                body_words = (f"{headline}. " + FILLER + " " + FILLER).split()[:word_target]
                s.add(Briefing(
                    cluster_id=cluster.id,
                    headline=headline,
                    body=" ".join(body_words),
                    word_count=len(body_words),
                    confidence=PYRNG.choice(["high", "high", "medium"]),
                    source_links=links[:4],
                    embedding=unit_vector(cluster_center, 0.02),
                    published_at=cluster.first_seen_at,
                    expires_at=cluster.first_seen_at + timedelta(hours=48),
                    projection=[float(x) for x in RNG.normal(0, 10, 3)],
                ))

        await s.flush()

        # -- today's feed for each user --------------------------------------
        briefings = (await s.execute(select(Briefing))).scalars().all()
        today = now.strftime("%Y-%m-%d")
        for u in users:
            ranked = PYRNG.sample(briefings, min(20, len(briefings)))
            for pos, b in enumerate(ranked):
                s.add(FeedItem(user_id=u.id, briefing_id=b.id, rank_score=1.0 - pos * 0.01,
                               rank_position=pos, feed_date=today))

        log.info("seed.done", users=len(users), raw_items=n_items,
                 clusters=n_clusters, briefings=len(briefings))


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
