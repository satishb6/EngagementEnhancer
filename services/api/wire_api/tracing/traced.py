"""@traced — emitting an event must be one line at the call site, or people
stop doing it.

Usage:

    @traced(Stage.BRIEF, entity_type="cluster")
    async def write_briefing(session, cluster, *, _trace_payload): ...

or as a context manager when you need to add payload mid-flight:

    async with traced_span(session, Stage.EMBED, entity_id=str(item.id)) as span:
        span.payload["batch"] = 64
"""

import functools
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models.base import utcnow, uuid7
from wire_api.models.tracing import EventStatus, Stage
from wire_api.tracing.context import current_trace
from wire_api.tracing.emit import emit_event

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Span:
    trace_id: uuid.UUID
    span_id: uuid.UUID
    parent_span_id: uuid.UUID | None
    stage: Stage
    entity_type: str = ""
    entity_id: str = ""
    user_id: uuid.UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@asynccontextmanager
async def traced_span(
    session: AsyncSession,
    stage: Stage,
    *,
    entity_type: str = "",
    entity_id: str = "",
    user_id: uuid.UUID | None = None,
    emit_start: bool = False,
) -> AsyncIterator[Span]:
    ctx = current_trace()
    span = Span(
        trace_id=ctx.trace_id,
        span_id=uuid7(),
        parent_span_id=ctx.span_id,
        stage=stage,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
    )
    # child spans opened inside this block get this span as parent
    prev_span_id = ctx.span_id
    ctx.span_id = span.span_id

    started = utcnow()
    t0 = time.perf_counter()
    if emit_start:
        await emit_event(
            session, trace_id=span.trace_id, span_id=span.span_id,
            parent_span_id=span.parent_span_id, stage=stage, status=EventStatus.STARTED,
            entity_type=entity_type, entity_id=entity_id, user_id=user_id,
            started_at=started,
        )
    try:
        yield span
    except Exception as exc:
        await emit_event(
            session, trace_id=span.trace_id, span_id=span.span_id,
            parent_span_id=span.parent_span_id, stage=stage, status=EventStatus.FAILED,
            entity_type=span.entity_type, entity_id=span.entity_id, user_id=span.user_id,
            started_at=started, ended_at=utcnow(),
            duration_ms=(time.perf_counter() - t0) * 1000,
            payload=span.payload,
            error={"type": type(exc).__name__, "message": str(exc)[:2000]},
        )
        raise
    else:
        await emit_event(
            session, trace_id=span.trace_id, span_id=span.span_id,
            parent_span_id=span.parent_span_id, stage=stage, status=EventStatus.SUCCEEDED,
            entity_type=span.entity_type, entity_id=span.entity_id, user_id=span.user_id,
            started_at=started, ended_at=utcnow(),
            duration_ms=(time.perf_counter() - t0) * 1000,
            payload=span.payload,
        )
    finally:
        ctx.span_id = prev_span_id


def traced(
    stage: Stage, *, entity_type: str = ""
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator form. The wrapped function must accept a `session` kwarg or
    first positional arg of type AsyncSession, and may accept `_span` to
    attach payload."""

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            session = kwargs.get("session")
            if session is None:
                session = next((a for a in args if isinstance(a, AsyncSession)), None)
            if session is None:
                raise TypeError(f"@traced({stage}) needs an AsyncSession argument")
            async with traced_span(session, stage, entity_type=entity_type) as span:
                if "_span" in fn.__code__.co_varnames:
                    kwargs["_span"] = span  # type: ignore[assignment]
                return await fn(*args, **kwargs)

        return wrapper

    return decorator
