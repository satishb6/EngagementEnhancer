"""The corpus pipeline: embed → cluster → brief → expire.

Runs once per cycle for ALL users. The invariant that keeps the business
alive: briefing generation count per cycle equals new-or-changed cluster
count, and is completely independent of user count.
"""

import json
import re
from datetime import timedelta
from typing import Any

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.agents.prompts import EDITOR
from wire_api.db import session_scope
from wire_api.dbcompat import knn
from wire_api.logging import get_logger
from wire_api.models import (
    Briefing,
    Cluster,
    ClusterMember,
    RawItem,
)
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.providers import Capability, Message, get_router
from wire_api.settings import get_settings
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


# --------------------------------------------------------------------------- #
# Stage 1 — Embed
# --------------------------------------------------------------------------- #
async def embed_new_items(session: AsyncSession) -> int:
    """Batch-embed raw items that don't have embeddings yet."""
    settings = get_settings()
    router = get_router()
    total = 0
    while True:
        items = (
            (
                await session.execute(
                    select(RawItem)
                    .where(RawItem.embedded_at.is_(None))
                    .order_by(RawItem.created_at)
                    .limit(settings.embed_batch_size)
                )
            )
            .scalars()
            .all()
        )
        if not items:
            break
        async with traced_span(session, Stage.EMBED, entity_type="raw_item_batch") as span:
            binding = await router.resolve(Capability.EMBEDDING, None, session)
            texts = [f"{i.title}\n\n{i.body[:4000]}" for i in items]
            result = await binding.provider.embed(texts)
            for item, vector in zip(items, result.vectors, strict=True):
                item.embedding = vector
                item.embedded_at = utcnow()
            span.payload.update({
                "batch_size": len(items),
                "provider": result.meta.provider_id,
                "model": result.meta.model_id,
                "input_tokens": result.input_tokens,
                "cost_cents": result.meta.cost_cents,
            })
        total += len(items)
        await session.flush()
    return total


# --------------------------------------------------------------------------- #
# Stage 2 — Cluster
# --------------------------------------------------------------------------- #
async def cluster_new_items(session: AsyncSession) -> int:
    """Assign embedded-but-unclustered items to clusters.

    Similarity to an existing centroid above the threshold joins that cluster;
    otherwise a new cluster opens. Candidates are time-windowed to 72h so
    clustering stays O(recent), not O(all)."""
    settings = get_settings()
    threshold = settings.cluster_similarity_threshold
    window_start = utcnow() - timedelta(hours=settings.cluster_window_hours)

    items = (
        (
            await session.execute(
                select(RawItem)
                .where(RawItem.embedded_at.is_not(None), RawItem.clustered_at.is_(None))
                .order_by(RawItem.created_at)
                .limit(2000)
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return 0

    clustered = 0
    async with traced_span(session, Stage.CLUSTER, entity_type="raw_item_batch") as span:
        for item in items:
            vec = np.asarray(item.embedding, dtype=np.float64)
            # nearest recent centroid — indexed SQL on PG, numpy on SQLite
            neighbours = await knn(
                session, Cluster, Cluster.centroid, list(vec),
                limit=1,
                base_query=select(Cluster).where(Cluster.last_grown_at >= window_start),
            )

            if neighbours and neighbours[0][1] >= threshold:
                cluster, similarity = neighbours[0]
                # incremental centroid update
                centroid = np.asarray(cluster.centroid, dtype=np.float64)
                n = cluster.member_count
                new_centroid = (centroid * n + vec) / (n + 1)
                norm = np.linalg.norm(new_centroid) or 1.0
                cluster.centroid = list((new_centroid / norm).astype(float))
                cluster.member_count = n + 1
                cluster.last_grown_at = utcnow()
            else:
                cluster = Cluster(
                    centroid=list(vec.astype(float)),
                    member_count=1,
                    first_seen_at=utcnow(),
                    last_grown_at=utcnow(),
                )
                session.add(cluster)
                await session.flush()
                similarity = 1.0

            session.add(ClusterMember(cluster_id=cluster.id, raw_item_id=item.id,
                                      similarity=similarity))
            item.clustered_at = utcnow()
            clustered += 1
        span.payload["count"] = clustered
    await session.flush()
    return clustered


# --------------------------------------------------------------------------- #
# Stage 3 — Brief
# --------------------------------------------------------------------------- #
_BANNED_ADJECTIVES = {
    "devastating", "groundbreaking", "controversial", "stunning", "historic",
    "shocking", "incredible", "amazing", "terrifying", "unprecedented",
}


def _validate_briefing(data: dict[str, Any]) -> str | None:
    """Return an error string, or None if the briefing passes the gates."""
    headline = str(data.get("headline", ""))
    body = str(data.get("body", ""))
    if not headline or not body:
        return "missing headline or body"
    if len(headline.split()) > 9:
        return f"headline over 9 words: {len(headline.split())}"
    if ":" in headline or "?" in headline:
        return "headline contains a colon or question mark"
    words = body.split()
    if len(words) > 60:
        return f"body over 60 words: {len(words)}"
    if len(words) < 35:
        return f"body implausibly short: {len(words)}"
    lowered = {w.strip(".,;!").lower() for w in words}
    hits = lowered & _BANNED_ADJECTIVES
    if hits:
        return f"judgement adjectives present: {sorted(hits)}"
    return None


def _rank_source_links(members: list[tuple[RawItem, float]]) -> list[dict[str, Any]]:
    """All source URLs from the cluster, deduped by domain, authority-ranked."""
    authority = ["reuters.com", "apnews.com", "ft.com", "bloomberg.com", "nature.com",
                 "wsj.com", "nytimes.com", "theverge.com", "arstechnica.com", "wired.com"]

    def rank(domain: str) -> int:
        return authority.index(domain) if domain in authority else len(authority)

    seen: set[str] = set()
    links: list[dict[str, Any]] = []
    for item, _sim in sorted(members, key=lambda pair: rank(pair[0].domain)):
        if item.domain in seen:
            continue
        seen.add(item.domain)
        links.append({"url": item.canonical_url, "domain": item.domain, "title": item.title})
    return links


async def brief_clusters(session: AsyncSession) -> int:
    """Generate briefings for clusters that need one: no briefing yet, or
    membership grew by more than the regen threshold since it was written."""
    settings = get_settings()
    router = get_router()

    # clusters needing a briefing
    have = select(Briefing.cluster_id)
    fresh_needed = (
        (
            await session.execute(
                select(Cluster).where(Cluster.id.not_in(have), Cluster.member_count >= 1)
            )
        )
        .scalars()
        .all()
    )
    grown = (
        (
            await session.execute(
                select(Cluster)
                .join(Briefing, Briefing.cluster_id == Cluster.id)
                .where(
                    Cluster.briefed_member_count > 0,
                    Cluster.member_count
                    > Cluster.briefed_member_count * (1.0 + settings.briefing_regen_growth),
                )
            )
        )
        .scalars()
        .all()
    )

    generated = 0
    for cluster in [*fresh_needed, *grown]:
        member_rows = (
            await session.execute(
                select(RawItem, ClusterMember.similarity)
                .join(ClusterMember, ClusterMember.raw_item_id == RawItem.id)
                .where(ClusterMember.cluster_id == cluster.id)
                .order_by(ClusterMember.similarity.desc())
                .limit(12)
            )
        ).all()
        members = [(row.RawItem, float(row.similarity)) for row in member_rows]
        if not members:
            continue

        reports = [
            {
                "title": item.title,
                "body": item.body[:2000],
                "source_domain": item.domain,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item, _s in members
        ]

        async with traced_span(
            session, Stage.BRIEF, entity_type="cluster", entity_id=str(cluster.id)
        ) as span:
            binding = await router.resolve(Capability.TEXT, None, session)
            user_msg = json.dumps({"reports": reports}, ensure_ascii=False)
            data: dict[str, Any] | None = None
            error = ""
            total_cost = 0.0

            for attempt in range(2):  # reject and retry once if over ceiling
                prompt_msgs = [Message("system", EDITOR), Message("user", user_msg)]
                if attempt == 1 and error:
                    prompt_msgs.append(Message(
                        "user",
                        f"Your previous output failed validation: {error}. "
                        "Return corrected strict JSON only.",
                    ))
                result = await binding.provider.complete(prompt_msgs, max_tokens=600)
                total_cost += result.meta.cost_cents
                match = _JSON_RE.search(result.text)
                if not match:
                    error = "no JSON object in response"
                    continue
                try:
                    candidate = json.loads(match.group())
                except json.JSONDecodeError as exc:
                    error = f"invalid JSON: {exc}"
                    continue
                problem = _validate_briefing(candidate)
                if problem:
                    error = problem
                    span.payload["retry_reason"] = problem
                    continue
                data = candidate
                break

            span.payload.update({
                "provider": binding.provider_id,
                "model": result.meta.model_id,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_cents": total_cost,
                "prompt": user_msg[:4000],
                "response": result.text[:4000],
            })

            if data is None:
                span.payload["gave_up"] = error
                log.warning("brief.validation_failed", cluster=str(cluster.id), error=error)
                continue

            body = str(data["body"])
            embed_binding = await router.resolve(Capability.EMBEDDING, None, session)
            embed_result = await embed_binding.provider.embed([f"{data['headline']}\n{body}"])

            existing = (
                await session.execute(
                    select(Briefing).where(Briefing.cluster_id == cluster.id)
                )
            ).scalar_one_or_none()
            links = _rank_source_links(members)
            now = utcnow()
            if existing is None:
                session.add(Briefing(
                    cluster_id=cluster.id,
                    headline=str(data["headline"]),
                    body=body,
                    word_count=len(body.split()),
                    confidence=str(data.get("confidence", "medium")),
                    source_links=links,
                    claims=list(data.get("claims", [])),
                    embedding=embed_result.vectors[0],
                    published_at=now,
                    expires_at=now + timedelta(hours=settings.briefing_expiry_hours),
                ))
            else:
                existing.headline = str(data["headline"])
                existing.body = body
                existing.word_count = len(body.split())
                existing.confidence = str(data.get("confidence", "medium"))
                existing.source_links = links
                existing.claims = list(data.get("claims", []))
                existing.embedding = embed_result.vectors[0]
                existing.expires_at = now + timedelta(hours=settings.briefing_expiry_hours)
                existing.expired = False
            cluster.briefed_member_count = cluster.member_count
            span.payload["word_count"] = len(body.split())
            generated += 1
        await session.flush()

    return generated


# --------------------------------------------------------------------------- #
# Stage 4 — Expire
# --------------------------------------------------------------------------- #
async def expire_briefings(session: AsyncSession) -> int:
    """Soft-delete briefings past their expiry. Kept for analytics + Lattice."""
    result = await session.execute(
        update(Briefing)
        .where(Briefing.expires_at < utcnow(), Briefing.expired.is_(False))
        .values(expired=True)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


# --------------------------------------------------------------------------- #
# The cycle
# --------------------------------------------------------------------------- #
async def run_corpus_cycle() -> dict[str, int]:
    """One full corpus pass. The generation count here is a function of the
    news, never of the user count — see tests/test_corpus_invariant.py."""
    async with session_scope() as session:
        embedded = await embed_new_items(session)
        clustered = await cluster_new_items(session)
        briefed = await brief_clusters(session)
        expired = await expire_briefings(session)
    metrics = {"embedded": embedded, "clustered": clustered,
               "briefed": briefed, "expired": expired}
    log.info("corpus.cycle", **metrics)
    return metrics
