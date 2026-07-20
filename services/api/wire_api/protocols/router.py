"""Protocol management: the user's source set. Onboarding bootstraps it;
the Studio editor maintains it."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from wire_api.auth.deps import DB, CurrentUser
from wire_api.models import ProtocolSource, Source, SourceKind, UserProtocol

router = APIRouter(prefix="/protocol", tags=["protocols"])

# Curated feeds for the onboarding domains — real, working RSS endpoints.
KNOWN_FEEDS: dict[str, str] = {
    "reuters.com": "https://www.reutersagency.com/feed/?best-topics=tech&post_type=best",
    "apnews.com": "https://rsshub.app/apnews/topics/apf-topnews",
    "theverge.com": "https://www.theverge.com/rss/index.xml",
    "arstechnica.com": "https://feeds.arstechnica.com/arstechnica/index",
    "ft.com": "https://www.ft.com/technology?format=rss",
    "bloomberg.com": "https://feeds.bloomberg.com/technology/news.rss",
    "wired.com": "https://www.wired.com/feed/rss",
    "nature.com": "https://www.nature.com/nature.rss",
    "techcrunch.com": "https://techcrunch.com/feed/",
    "hnrss.org": "https://hnrss.org/frontpage",
}


async def _default_protocol(session: Any, user_id: uuid.UUID) -> UserProtocol:
    proto = (
        await session.execute(
            select(UserProtocol).where(
                UserProtocol.user_id == user_id, UserProtocol.is_default.is_(True)
            )
        )
    ).scalar_one_or_none()
    if proto is None:
        proto = UserProtocol(user_id=user_id, name="My wire", is_default=True)
        session.add(proto)
        await session.flush()
    return proto


async def _get_or_create_source(session: Any, domain: str, feed_url: str) -> Source:
    source = (
        await session.execute(
            select(Source).where(Source.kind == SourceKind.RSS, Source.name == domain)
        )
    ).scalar_one_or_none()
    if source is None:
        source = Source(kind=SourceKind.RSS, name=domain, domain=domain,
                        config={"url": feed_url})
        session.add(source)
        await session.flush()
    return source


@router.get("")
async def get_protocol(user: CurrentUser, session: DB) -> dict[str, Any]:
    proto = await _default_protocol(session, user.id)
    rows = (
        await session.execute(
            select(ProtocolSource, Source)
            .join(Source, Source.id == ProtocolSource.source_id)
            .where(ProtocolSource.protocol_id == proto.id)
        )
    ).all()
    await session.commit()
    return {
        "protocol_id": str(proto.id),
        "name": proto.name,
        "region_weights": proto.region_weights,
        "sources": [
            {"link_id": str(ps.id), "source_id": str(s.id), "kind": s.kind.value,
             "name": s.name, "domain": s.domain, "url": s.config.get("url", ""),
             "weight": ps.weight}
            for ps, s in rows
        ],
    }


class BootstrapIn(BaseModel):
    domains: list[str] = Field(default_factory=list, max_length=30)
    topics: list[str] = Field(default_factory=list, max_length=12)


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap(body: BootstrapIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    """Onboarding handoff: chosen domains become live RSS sources on the
    default protocol; chosen topics seed region weights so day-one ranking
    already leans the right way."""
    proto = await _default_protocol(session, user.id)

    existing = set(
        (
            await session.execute(
                select(ProtocolSource.source_id).where(ProtocolSource.protocol_id == proto.id)
            )
        ).scalars()
    )
    added = 0
    for domain in body.domains:
        domain = domain.strip().lower().removeprefix("www.")
        feed_url = KNOWN_FEEDS.get(domain, f"https://{domain}/feed")
        source = await _get_or_create_source(session, domain, feed_url)
        if source.id not in existing:
            session.add(ProtocolSource(protocol_id=proto.id, source_id=source.id))
            existing.add(source.id)
            added += 1

    if body.topics:
        weights = dict(proto.region_weights or {})
        for topic in body.topics:
            weights[topic] = max(weights.get(topic, 1.0), 1.4)
        proto.region_weights = weights

    await session.commit()
    return {"sources_added": added, "topics_boosted": len(body.topics)}


class AddSourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    name: str = ""


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def add_source(body: AddSourceIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    from urllib.parse import urlparse

    parsed = urlparse(body.url if "://" in body.url else f"https://{body.url}")
    domain = parsed.netloc.removeprefix("www.")
    if not domain:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That doesn't look like a URL.")
    proto = await _default_protocol(session, user.id)
    source = await _get_or_create_source(session, body.name or domain, parsed.geturl())
    exists = (
        await session.execute(
            select(ProtocolSource.id).where(
                ProtocolSource.protocol_id == proto.id,
                ProtocolSource.source_id == source.id,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(ProtocolSource(protocol_id=proto.id, source_id=source.id))
    await session.commit()
    return {"source_id": str(source.id), "domain": source.domain}


@router.delete("/sources/{link_id}")
async def remove_source(link_id: uuid.UUID, user: CurrentUser, session: DB) -> dict[str, str]:
    proto = await _default_protocol(session, user.id)
    result = await session.execute(
        delete(ProtocolSource).where(
            ProtocolSource.id == link_id, ProtocolSource.protocol_id == proto.id
        )
    )
    await session.commit()
    if not result.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in your protocol.")
    return {"removed": str(link_id)}
