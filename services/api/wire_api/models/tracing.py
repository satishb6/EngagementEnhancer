"""The trace spine. Append-only. Every backend operation writes here; the
Wire Room reads nothing else."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from wire_api.models.base import Base, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class Stage(enum.StrEnum):
    FETCH = "fetch"
    EMBED = "embed"
    CLUSTER = "cluster"
    BRIEF = "brief"
    RANK = "rank"
    GENERATE = "generate"
    PUBLISH = "publish"


class EventStatus(enum.StrEnum):
    STARTED = "started"
    PROGRESS = "progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PipelineEvent(Base, PKMixin, TimestampMixin):
    __tablename__ = "pipeline_event"

    trace_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    span_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    stage: Mapped[Stage] = mapped_column(Enum(Stage, native_enum=False, length=12), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    # nullable — corpus stages aren't user-scoped
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, native_enum=False, length=12), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    duration_ms: Mapped[float | None] = mapped_column(Float)
    # stage-specific; for model calls MUST include provider, model, prompt,
    # response, input_tokens, output_tokens, cost_cents. Redaction guard
    # rejects anything key-shaped before it gets here.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONField)
    # retention: prompt/response stripped after N days, metrics kept forever
    payload_stripped: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_pipeline_event_trace", "trace_id", "created_at"),
        Index("ix_pipeline_event_stage_created", "stage", "created_at"),
        Index("ix_pipeline_event_user_created", "user_id", "created_at"),
    )
