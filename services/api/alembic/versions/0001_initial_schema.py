"""Initial schema — all eight domains plus the trace spine.

This first migration intentionally builds from the reviewed model metadata
(the models ARE the reviewed DDL for v0). Later migrations must be written
as explicit ops; never re-run create_all once revision 0002 exists.

Revision ID: 0001
Revises:
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op

from wire_api.models import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
