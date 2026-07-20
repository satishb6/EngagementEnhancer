"""Event emission: one insert into pipeline_event + one Redis publish so the
Wire Room sees it live even when the writer is a worker on another machine."""

import uuid
from datetime import datetime
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.bus import CHANNEL, get_bus
from wire_api.logging import get_logger
from wire_api.models import PipelineEvent
from wire_api.models.base import utcnow, uuid7
from wire_api.models.tracing import EventStatus, Stage
from wire_api.tracing.redaction import assert_payload_clean

log = get_logger(__name__)

__all__ = ["CHANNEL", "emit_event"]


def _serialise(event: PipelineEvent) -> bytes:
    return orjson.dumps(
        {
            "id": str(event.id),
            "trace_id": str(event.trace_id),
            "span_id": str(event.span_id),
            "parent_span_id": str(event.parent_span_id) if event.parent_span_id else None,
            "stage": event.stage.value,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "user_id": str(event.user_id) if event.user_id else None,
            "status": event.status.value,
            "started_at": event.started_at.isoformat() if event.started_at else None,
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "duration_ms": event.duration_ms,
            "payload": event.payload,
            "error": event.error,
            "created_at": (event.created_at or utcnow()).isoformat(),
        }
    )


async def emit_event(
    session: AsyncSession,
    *,
    trace_id: uuid.UUID,
    span_id: uuid.UUID | None = None,
    parent_span_id: uuid.UUID | None = None,
    stage: Stage,
    status: EventStatus,
    entity_type: str = "",
    entity_id: str = "",
    user_id: uuid.UUID | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_ms: float | None = None,
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> PipelineEvent:
    """Insert + publish. Raises RedactionError on credential-shaped payloads."""
    event = PipelineEvent(
        id=uuid7(),
        trace_id=trace_id,
        span_id=span_id or uuid7(),
        parent_span_id=parent_span_id,
        stage=stage,
        status=status,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        payload=assert_payload_clean(payload or {}),
        error=error,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(event)
    await session.flush()
    try:
        await get_bus().publish(_serialise(event).decode())
    except Exception as exc:  # noqa: BLE001 — live stream is best-effort; the DB row is truth
        log.warning("trace.publish_failed", error=str(exc))
    return event
