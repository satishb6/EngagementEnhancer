"""Per-user zone: feed items, swipes, takes."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from wire_api.models.base import EMBED_DIM, Base, PKMixin, TimestampMixin


class SwipeDirection(enum.StrEnum):
    LEFT = "left"
    RIGHT = "right"


class TakeSource(enum.StrEnum):
    AUTHORED = "authored"
    SUGGESTED = "suggested"


class FeedItem(Base, PKMixin, TimestampMixin):
    """briefing × user, with rank score and served_at."""

    __tablename__ = "feed_item"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    briefing_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("briefing.id", ondelete="CASCADE"), nullable=False
    )
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_position: Mapped[int] = mapped_column(Integer, default=0)
    feed_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    swiped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_feed_user_briefing_date", "user_id", "briefing_id", "feed_date", unique=True),
        # hot path: unserved feed items per user
        Index(
            "ix_feed_item_unserved", "user_id", "rank_position",
            postgresql_where=text("served_at IS NULL"),
        ),
        Index("ix_feed_item_user_date", "user_id", "feed_date"),
    )


class Swipe(Base, PKMixin, TimestampMixin):
    __tablename__ = "swipe"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    feed_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("feed_item.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[SwipeDirection] = mapped_column(
        Enum(SwipeDirection, native_enum=False, length=8), nullable=False
    )
    swiped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dwell_ms: Mapped[int] = mapped_column(Integer, default=0)
    # idempotency: client retries must not double-count
    client_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    undone: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("uq_swipe_feed_item_event", "feed_item_id", "client_event_id", unique=True),
        Index("ix_swipe_user_created", "user_id", "created_at"),
    )


class Take(Base, PKMixin, TimestampMixin):
    """The user's opinion on a kept briefing."""

    __tablename__ = "take"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    briefing_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("briefing.id", ondelete="CASCADE"), nullable=False
    )
    feed_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("feed_item.id", ondelete="SET NULL")
    )
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    audio_ref: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    stance: Mapped[str] = mapped_column(String(24), default="")
    stance_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[TakeSource] = mapped_column(
        Enum(TakeSource, native_enum=False, length=12), default=TakeSource.AUTHORED
    )
    # the suggestion the user started from, for edit-distance / voice-match
    suggested_text: Mapped[str] = mapped_column(Text, default="")
    edit_distance_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))

    __table_args__ = (
        Index("uq_take_user_briefing", "user_id", "briefing_id", unique=True),
        Index(
            "ix_take_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
