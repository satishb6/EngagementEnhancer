"""Model base: UUIDv7 primary keys, timestamps, and cross-database types.

WIRE runs on two databases:
- Postgres 16 + pgvector (production scale path)
- SQLite (lite mode: zero-infra local dev + free-tier Hugging Face Spaces)

The custom types below compile to the right thing on each. Vector search
uses pgvector SQL on Postgres and a numpy fallback on SQLite (see
wire_api/vectors.py).
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import uuid_utils
from sqlalchemy import DateTime, MetaData, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

# One dimension everywhere. Cloud embeddings are padded/truncated to this.
EMBED_DIM = 1536

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Generic UUID: native uuid on PG, CHAR(32) on SQLite.
GUID = Uuid(as_uuid=True)

# JSON that becomes JSONB on Postgres.
JSONField = JSON().with_variant(JSONB(), "postgresql")


class TZDateTime(TypeDecorator[datetime]):
    """Timestamps are UTC-aware in Python on every backend.

    SQLite stores datetimes as ISO strings and compares them AS STRINGS, so
    aware ("…+00:00") and naive values must never mix in storage — a query
    parameter with an offset suffix compares wrongly against naive rows
    (this once expired every briefing a day early). Fix: on non-Postgres
    backends every bound value is normalised to naive UTC, and every value
    read back gets UTC re-attached."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if (
            value is not None
            and dialect.name != "postgresql"
            and getattr(value, "tzinfo", None) is not None
        ):
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is not None and getattr(value, "tzinfo", None) is None:
            return value.replace(tzinfo=UTC)
        return value


class EmbeddingVector(TypeDecorator[list[float]]):
    """pgvector Vector on Postgres; JSON text on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBED_DIM))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps([float(v) for v in value])

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value)

    class comparator_factory(Text.Comparator):  # type: ignore[misc] # noqa: N801
        def cosine_distance(self, other: Any) -> Any:
            """Only valid on Postgres — callers must branch (wire_api.vectors)."""
            return self.op("<=>")(other)


def uuid7() -> uuid.UUID:
    """Time-ordered UUIDs so PK order ≈ insertion order (index-friendly)."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class PKMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )
