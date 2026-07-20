"""Learning-loop state: style profiles, format matrix, timing curves, and the
audit trail that makes every ranking decision explainable."""

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from wire_api.models.base import Base, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class StyleProfile(Base, PKMixin, TimestampMixin):
    """Loop 2 — VOICE. Rolling profile maintained by the Stenographer."""

    __tablename__ = "style_profile"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    sentence_length_mean: Mapped[float] = mapped_column(Float, default=0.0)
    sentence_length_sd: Mapped[float] = mapped_column(Float, default=0.0)
    register: Mapped[str] = mapped_column(String(20), default="conversational")
    hedging_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    profanity: Mapped[bool] = mapped_column(default=False)
    question_frequency: Mapped[float] = mapped_column(Float, default=0.0)
    signature_constructions: Mapped[list[str]] = mapped_column(JSONField, default=list)
    avoided_words: Mapped[list[str]] = mapped_column(JSONField, default=list)
    stance_distribution: Mapped[dict[str, float]] = mapped_column(JSONField, default=dict)
    sample_sentences: Mapped[list[str]] = mapped_column(JSONField, default=list)
    take_count: Mapped[int] = mapped_column(Integer, default=0)


class FormatStat(Base, PKMixin, TimestampMixin):
    """Loop 3 — FORMAT. (topic_region × content_type × platform) → success,
    Bayesian-smoothed so early data doesn't overfit."""

    __tablename__ = "format_stat"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    region_key: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    picks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    engagement_sum: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        Index("uq_format_stat_key", "user_id", "region_key", "content_type", "platform",
              unique=True),
    )


class TimingStat(Base, PKMixin, TimestampMixin):
    """Loop 4 — TIMING. Per-platform, per-weekday hourly engagement curve."""

    __tablename__ = "timing_stat"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    posts: Mapped[int] = mapped_column(Integer, default=0)
    engagement_sum: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        Index("uq_timing_stat_key", "user_id", "platform", "weekday", "hour", unique=True),
    )


class LearningEvent(Base, PKMixin, TimestampMixin):
    """Every learning update is a discrete, logged event carrying which human
    action caused it. 'Why am I being shown this' reads from here."""

    __tablename__ = "learning_event"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    loop: Mapped[str] = mapped_column(String(12), nullable=False)  # taste|voice|format|timing
    trigger_kind: Mapped[str] = mapped_column(String(24), nullable=False)  # swipe|take|pick|publish
    trigger_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)

    __table_args__ = (
        Index("ix_learning_event_user_loop", "user_id", "loop", "created_at"),
    )
