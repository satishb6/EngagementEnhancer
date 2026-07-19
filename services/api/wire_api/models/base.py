"""Model base: UUIDv7 primary keys, timestamps, the embedding dimension."""

import uuid
from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# One dimension everywhere. Cloud embeddings (text-embedding-3-small) are
# native 1536; the local sentence-transformers adapter L2-normalises and
# zero-pads to this. Changing it is a migration, not a config flip.
EMBED_DIM = 1536

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def uuid7() -> uuid.UUID:
    """Time-ordered UUIDs so PK order ≈ insertion order (index-friendly)."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class PKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid7
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
