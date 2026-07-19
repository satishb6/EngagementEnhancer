"""The shared corpus. This is the cost-critical zone: every row here is
written once per news event, NEVER once per user. If a feature makes this
zone grow with user count, the feature is wrong."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from wire_api.models.base import EMBED_DIM, Base, PKMixin, TimestampMixin


class RawItem(Base, PKMixin, TimestampMixin):
    __tablename__ = "raw_item"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.id", ondelete="SET NULL"), nullable=True
    )
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(300), default="")
    domain: Mapped[str] = mapped_column(String(200), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # sha256 of normalised content — dedup at fetch time so unchanged items
    # cost nothing downstream
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clustered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        # hot path: new items awaiting embedding / clustering
        Index(
            "ix_raw_item_unembedded", "created_at",
            postgresql_where=text("embedded_at IS NULL"),
        ),
        Index("ix_raw_item_domain", "domain"),
    )


class Cluster(Base, PKMixin, TimestampMixin):
    """A deduplicated news event. Holds the centroid embedding."""

    __tablename__ = "cluster"

    centroid: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    # member_count when the current briefing was written; regenerate when
    # membership grows by >40%
    briefed_member_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_grown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # coarse topic region key for the Lattice + per-region taste weights
    region_key: Mapped[str] = mapped_column(String(80), default="")

    __table_args__ = (
        Index(
            "ix_cluster_centroid_hnsw",
            "centroid",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"centroid": "vector_cosine_ops"},
        ),
        Index("ix_cluster_last_grown", "last_grown_at"),
    )


class ClusterMember(Base, PKMixin, TimestampMixin):
    __tablename__ = "cluster_member"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cluster.id", ondelete="CASCADE"), nullable=False
    )
    raw_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("raw_item.id", ondelete="CASCADE"), nullable=False
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("uq_cluster_member_item", "raw_item_id", unique=True),
        Index("ix_cluster_member_cluster", "cluster_id"),
    )


class Briefing(Base, PKMixin, TimestampMixin):
    """ONE per cluster. The neutral substrate the user's opinion sits on."""

    __tablename__ = "briefing"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cluster.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # 50–60 words, hard ceiling 60
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str] = mapped_column(String(12), default="medium")  # high|medium|low
    contested: Mapped[bool] = mapped_column(Boolean, default=False)
    # [{"url":..., "domain":..., "title":...}] ranked by domain authority, deduped by domain
    source_links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # soft delete: expired briefings leave the active pool, kept for analytics
    expired: Mapped[bool] = mapped_column(Boolean, default=False)
    # cached 3D UMAP projection for the Lattice
    projection: Mapped[list[float] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "ix_briefing_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_briefing_active", "published_at",
            postgresql_where=text("expired = false"),
        ),
    )
