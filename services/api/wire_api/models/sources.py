"""Sources and user protocols."""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


from wire_api.models.base import Base, EMBED_DIM, EmbeddingVector, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class SourceKind(enum.StrEnum):
    RSS = "rss"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    NEWSAPI = "newsapi"
    WEB = "web"


class Source(Base, PKMixin, TimestampMixin):
    __tablename__ = "source"

    kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, native_enum=False, length=16), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # per-type config: {"url": ...} for rss, {"subreddit": ...} for reddit,
    # {"channel_id"|"playlist_id"|"query": ...} for youtube, etc.
    config: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    domain: Mapped[str] = mapped_column(String(200), default="")
    poll_interval_s: Mapped[int] = mapped_column(Integer, default=900)
    # adaptive polling: sources that publish rarely get polled less
    last_polled_at_epoch: Mapped[float] = mapped_column(Float, default=0.0)
    consecutive_empty_polls: Mapped[int] = mapped_column(Integer, default=0)
    etag: Mapped[str] = mapped_column(String(300), default="")
    last_modified: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("uq_source_kind_name", "kind", "name", unique=True),
    )


class UserProtocol(Base, PKMixin, TimestampMixin):
    """A user's named source set + topic interest vector + filters."""

    __tablename__ = "user_protocol"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    interest_vector: Mapped[list[float] | None] = mapped_column(EmbeddingVector())
    # region key -> weight multiplier; lets a user like AI news but mute AI funding
    region_weights: Mapped[dict[str, float]] = mapped_column(JSONField, default=dict)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    is_default: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("ix_user_protocol_user", "user_id"),
    )


class ProtocolSource(Base, PKMixin, TimestampMixin):
    __tablename__ = "protocol_source"

    protocol_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user_protocol.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (
        Index("uq_protocol_source", "protocol_id", "source_id", unique=True),
    )
