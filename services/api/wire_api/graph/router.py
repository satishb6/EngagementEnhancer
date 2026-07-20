"""GET /graph — the Lattice's data. Positions come from a cached 3D
projection of real briefing embeddings (UMAP when installed, PCA otherwise),
seeding the client's force layout. Never random."""

import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter
from sqlalchemy import func, select

from wire_api.auth.deps import DB, CurrentUser
from wire_api.models import (
    Briefing,
    Cluster,
    Swipe,
    SwipeDirection,
    Take,
)

router = APIRouter(tags=["graph"])

EDGE_THRESHOLD = 0.60
MAX_NODES = 2000


def _project(vectors: np.ndarray) -> np.ndarray:
    """3D projection of embedding space. UMAP if available; PCA fallback keeps
    the semantic-proximity guarantee either way."""
    try:
        import umap  # type: ignore[import-not-found]

        reducer = umap.UMAP(n_components=3, random_state=42, metric="cosine")
        return np.asarray(reducer.fit_transform(vectors), dtype=np.float64)
    except ImportError:
        centred = vectors - vectors.mean(axis=0)
        _, _, vt = np.linalg.svd(centred, full_matrices=False)
        return centred @ vt[:3].T * 10.0


@router.get("/graph")
async def get_graph(user: CurrentUser, session: DB) -> dict[str, Any]:
    briefings = (
        (
            await session.execute(
                select(Briefing)
                .where(Briefing.embedding.is_not(None))
                .order_by(Briefing.published_at.desc())
                .limit(MAX_NODES)
            )
        )
        .scalars()
        .all()
    )
    if not briefings:
        return {"nodes": [], "edges": [], "regions": []}

    # cached projections where they exist; project + cache the rest in one pass
    missing = [b for b in briefings if not b.projection]
    if missing:
        vectors = np.asarray([b.embedding for b in briefings], dtype=np.float64)
        coords = _project(vectors)
        for b, xyz in zip(briefings, coords, strict=True):
            b.projection = [round(float(v), 3) for v in xyz]
        await session.commit()

    # engagement + exposure per briefing for this user
    my_takes = {
        t.briefing_id: t
        for t in (
            await session.execute(select(Take).where(Take.user_id == user.id))
        ).scalars()
    }
    # right-swipes across ALL users = engagement volume
    from wire_api.models import FeedItem

    keep_counts = dict(
        (
            await session.execute(
                select(FeedItem.briefing_id, func.count())
                .join(Swipe, Swipe.feed_item_id == FeedItem.id)
                .where(Swipe.direction == SwipeDirection.RIGHT, Swipe.undone.is_(False))
                .group_by(FeedItem.briefing_id)
            )
        ).all()
    )

    cluster_ids = {b.cluster_id for b in briefings}
    clusters = {
        c.id: c
        for c in (
            await session.execute(select(Cluster).where(Cluster.id.in_(cluster_ids)))
        ).scalars()
    }

    nodes: list[dict[str, Any]] = []
    region_agg: dict[str, dict[str, Any]] = {}
    for b in briefings:
        take = my_takes.get(b.id)
        cluster = clusters.get(b.cluster_id)
        region = cluster.region_key if cluster else ""
        engagement = int(keep_counts.get(b.id, 0))
        nodes.append({
            "id": str(b.id),
            "kind": "briefing",
            "headline": b.headline,
            "position": b.projection,
            "region": region,
            "engagement": engagement,
            "has_take": take is not None,
            "published_count": 0,
            "last_touched": (take.updated_at if take else b.created_at).isoformat(),
            "created_at": b.created_at.isoformat(),
            "expired": b.expired,
        })
        if region:
            agg = region_agg.setdefault(region, {
                "key": region, "count": 0, "exposed": 0,
                "position": [0.0, 0.0, 0.0],
            })
            agg["count"] += 1
            agg["exposed"] += 1 if take is not None else 0
            agg["position"] = [
                p + float(q) for p, q in zip(agg["position"], b.projection or [0, 0, 0],
                                             strict=False)
            ]
    regions = []
    for agg in region_agg.values():
        n = max(agg["count"], 1)
        regions.append({
            "key": agg["key"], "count": agg["count"], "exposed": agg["exposed"],
            "position": [round(p / n, 3) for p in agg["position"]],
        })

    # edges: cosine similarity above threshold, k-NN capped so the payload
    # stays linear in node count
    vectors = np.asarray([b.embedding for b in briefings], dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms
    edges: list[dict[str, Any]] = []
    k = min(6, len(briefings) - 1)
    if k > 0:
        sims = unit @ unit.T
        np.fill_diagonal(sims, -1.0)
        for i in range(len(briefings)):
            neighbour_idx = np.argpartition(sims[i], -k)[-k:]
            for j in neighbour_idx:
                if j <= i:
                    continue
                strength = float(sims[i, j])
                if strength >= EDGE_THRESHOLD:
                    edges.append({
                        "source": str(briefings[i].id),
                        "target": str(briefings[int(j)].id),
                        "strength": round(strength, 3),
                    })

    return {"nodes": nodes, "edges": edges, "regions": regions}


@router.get("/graph/node/{briefing_id}")
async def node_detail(briefing_id: uuid.UUID, user: CurrentUser, session: DB) -> dict[str, Any]:
    """The Print panel: briefing, your take, what you published, how it did."""
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    ).scalar_one()
    take = (
        await session.execute(
            select(Take).where(Take.user_id == user.id, Take.briefing_id == briefing_id)
        )
    ).scalar_one_or_none()

    publications: list[dict[str, Any]] = []
    if take is not None:
        from wire_api.models import Artifact, GenerationJob, Publication

        pubs = (
            await session.execute(
                select(Publication)
                .join(Artifact, Artifact.id == Publication.artifact_id)
                .join(GenerationJob, GenerationJob.id == Artifact.job_id)
                .where(GenerationJob.take_id == take.id)
            )
        ).scalars()
        publications = [
            {"id": str(p.id), "status": p.status.value,
             "posted_at": p.posted_at.isoformat() if p.posted_at else None,
             "engagement": p.engagement}
            for p in pubs
        ]

    return {
        "briefing": {
            "id": str(briefing.id), "headline": briefing.headline, "body": briefing.body,
            "source_links": briefing.source_links, "confidence": briefing.confidence,
            "published_at": briefing.published_at.isoformat() if briefing.published_at else None,
        },
        "take": {"text": take.text_content, "stance": take.stance,
                 "source": take.source.value} if take else None,
        "publications": publications,
    }
