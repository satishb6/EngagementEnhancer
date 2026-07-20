"""Generation jobs and artifacts."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from wire_api.models.base import Base, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class JobState(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentType(enum.StrEnum):
    TEXT = "text"
    IMAGE = "image"
    GIF = "gif"
    VIDEO_SHORT = "video_short"
    VIDEO_LONG = "video_long"


class GenerationTier(enum.StrEnum):
    EAGER = "eager"          # auto on take submission: text, images, gifs
    ON_DEMAND = "on_demand"  # explicit user action + entitlement: short video
    GATED = "gated"          # explicit action + cost confirmation: long video


class GenerationJob(Base, PKMixin, TimestampMixin):
    __tablename__ = "generation_job"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    take_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("take.id", ondelete="SET NULL")
    )
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, native_enum=False, length=12), default=JobState.QUEUED
    )
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False, length=16), nullable=False
    )
    tier: Mapped[GenerationTier] = mapped_column(
        Enum(GenerationTier, native_enum=False, length=12), nullable=False
    )
    variant_index: Mapped[int] = mapped_column(Integer, default=0)
    target_platform: Mapped[str] = mapped_column(String(24), default="")
    provider_id: Mapped[str] = mapped_column(String(40), default="")
    model_id: Mapped[str] = mapped_column(String(80), default="")
    # cost estimated BEFORE the job runs, persisted alongside the result
    cost_estimate_cents: Mapped[int] = mapped_column(Integer, default=0)
    cost_actual_cents: Mapped[int | None] = mapped_column(Integer)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # set only when a request handler initiated this job; the tier gate
    # rejects VIDEO jobs where this is false
    user_initiated: Mapped[bool] = mapped_column(nullable=False, default=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONField)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime())

    __table_args__ = (
        # hot path: running jobs
        Index(
            "ix_generation_job_running", "user_id", "created_at",
            postgresql_where=text("state IN ('queued','running')"),
        ),
        Index("ix_generation_job_take", "take_id"),
    )


class Artifact(Base, PKMixin, TimestampMixin):
    __tablename__ = "artifact"

    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("generation_job.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, native_enum=False, length=16), nullable=False
    )
    variant_index: Mapped[int] = mapped_column(Integer, default=0)
    # text artifacts store the copy inline; media store a storage URI
    text_content: Mapped[str] = mapped_column(Text, default="")
    storage_uri: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    # TTL by tier: free 48h, paid 30d, then cold storage
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    cold_stored: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_artifact_user_created", "user_id", "created_at"),
        Index("ix_artifact_job", "job_id"),
    )
