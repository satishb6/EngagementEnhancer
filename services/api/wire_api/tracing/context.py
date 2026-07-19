"""Trace context propagation. A briefing generated from an item fetched an
hour ago shares a trace_id with that fetch — including across Celery hops."""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

from wire_api.models.base import uuid7


@dataclass
class TraceContext:
    trace_id: uuid.UUID = field(default_factory=uuid7)
    span_id: uuid.UUID | None = None

    def headers(self) -> dict[str, str]:
        """Serialise for Celery task kwargs / HTTP headers."""
        h = {"wire_trace_id": str(self.trace_id)}
        if self.span_id:
            h["wire_parent_span_id"] = str(self.span_id)
        return h

    @classmethod
    def from_headers(cls, headers: dict[str, str] | None) -> "TraceContext":
        if not headers or "wire_trace_id" not in headers:
            return cls()
        try:
            parent = headers.get("wire_parent_span_id")
            return cls(
                trace_id=uuid.UUID(headers["wire_trace_id"]),
                span_id=uuid.UUID(parent) if parent else None,
            )
        except ValueError:
            return cls()


_current: ContextVar[TraceContext | None] = ContextVar("wire_trace", default=None)


def current_trace() -> TraceContext:
    ctx = _current.get()
    if ctx is None:
        ctx = TraceContext()
        _current.set(ctx)
    return ctx


def set_trace(ctx: TraceContext) -> None:
    _current.set(ctx)


def clear_trace() -> None:
    _current.set(None)
