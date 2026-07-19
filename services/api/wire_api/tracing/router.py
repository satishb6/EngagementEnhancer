"""Wire Room data plane: live SSE stream, aggregates, trace reconstruction."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import orjson
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.db import get_session
from wire_api.models import PipelineEvent
from wire_api.models.base import utcnow
from wire_api.models.tracing import EventStatus, Stage
from wire_api.tracing.emit import CHANNEL, get_redis

router = APIRouter(prefix="/events", tags=["tracing"])


def _row_to_dict(e: PipelineEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "trace_id": str(e.trace_id),
        "span_id": str(e.span_id),
        "parent_span_id": str(e.parent_span_id) if e.parent_span_id else None,
        "stage": e.stage.value,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "user_id": str(e.user_id) if e.user_id else None,
        "status": e.status.value,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "ended_at": e.ended_at.isoformat() if e.ended_at else None,
        "duration_ms": e.duration_ms,
        "payload": e.payload,
        "error": e.error,
        "created_at": e.created_at.isoformat(),
    }


@router.get("/stream")
async def stream(
    stage: str | None = None,
    user_id: str | None = None,
    last_event_id: str | None = Query(default=None, alias="last_event_id"),
    session: AsyncSession = Depends(get_session),
) -> EventSourceResponse:
    """SSE stream of pipeline events, filterable by stage and user.

    On reconnect the client passes the last received event id and missed
    events are replayed from the DB before the live tail resumes.
    """

    async def generator() -> Any:
        # replay missed events first
        if last_event_id:
            try:
                after = uuid.UUID(last_event_id)
                q = (
                    select(PipelineEvent)
                    .where(PipelineEvent.id > after)
                    .order_by(PipelineEvent.id)
                    .limit(500)
                )
                if stage:
                    q = q.where(PipelineEvent.stage == Stage(stage))
                if user_id:
                    q = q.where(PipelineEvent.user_id == uuid.UUID(user_id))
                for row in (await session.execute(q)).scalars():
                    yield {"id": str(row.id), "event": "pipeline",
                           "data": orjson.dumps(_row_to_dict(row)).decode()}
            except ValueError:
                pass

        pubsub = get_redis().pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                data = orjson.loads(msg["data"])
                if stage and data.get("stage") != stage:
                    continue
                if user_id and data.get("user_id") != user_id:
                    continue
                yield {"id": data["id"], "event": "pipeline",
                       "data": orjson.dumps(data).decode()}
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()

    return EventSourceResponse(generator())


@router.get("/summary")
async def summary(
    window_minutes: int = 60,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Per-stage throughput, p50/p95 latency, error rate, and cost over a
    window. The Wire Room's meters read from here, never the raw log."""
    since = utcnow() - timedelta(minutes=window_minutes)

    q = (
        select(
            PipelineEvent.stage,
            func.count().label("events"),
            func.count().filter(PipelineEvent.status == EventStatus.FAILED).label("failures"),
            func.percentile_cont(0.5).within_group(PipelineEvent.duration_ms).label("p50"),
            func.percentile_cont(0.95).within_group(PipelineEvent.duration_ms).label("p95"),
        )
        .where(PipelineEvent.created_at >= since)
        .where(PipelineEvent.status.in_([EventStatus.SUCCEEDED, EventStatus.FAILED]))
        .group_by(PipelineEvent.stage)
    )
    stages: dict[str, dict[str, Any]] = {}
    for row in (await session.execute(q)).all():
        stages[row.stage.value] = {
            "events": row.events,
            "failures": row.failures,
            "error_rate": (row.failures / row.events) if row.events else 0.0,
            "p50_ms": float(row.p50) if row.p50 is not None else None,
            "p95_ms": float(row.p95) if row.p95 is not None else None,
            "cost_cents": 0.0,
        }

    cost_q = (
        select(
            PipelineEvent.stage,
            func.sum(sa.cast(PipelineEvent.payload["cost_cents"].astext, sa.Float)),
        )
        .where(PipelineEvent.created_at >= since)
        .where(PipelineEvent.payload.has_key("cost_cents"))
        .group_by(PipelineEvent.stage)
    )
    for stage_val, cost in (await session.execute(cost_q)).all():
        if stage_val.value in stages and cost is not None:
            stages[stage_val.value]["cost_cents"] = float(cost)

    return {"window_minutes": window_minutes, "stages": stages, "generated_at": utcnow().isoformat()}


@router.get("/trace/{trace_id}")
async def get_trace(
    trace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Reconstruct the complete journey of one item — every stage, every model
    call, every cost — from pipeline_event alone."""
    rows = (
        (
            await session.execute(
                select(PipelineEvent)
                .where(PipelineEvent.trace_id == trace_id)
                .order_by(PipelineEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    total_cost = sum(
        float(e.payload.get("cost_cents", 0) or 0) for e in rows if isinstance(e.payload, dict)
    )
    return {
        "trace_id": str(trace_id),
        "events": [_row_to_dict(e) for e in rows],
        "total_cost_cents": total_cost,
    }


@router.get("/recent")
async def recent(
    stage: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Last N events through a stage, newest first — the inspection panel."""
    rows = (
        (
            await session.execute(
                select(PipelineEvent)
                .where(PipelineEvent.stage == Stage(stage))
                .order_by(PipelineEvent.created_at.desc())
                .limit(min(limit, 200))
            )
        )
        .scalars()
        .all()
    )
    return [_row_to_dict(e) for e in rows]
