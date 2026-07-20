"""Cross-database helpers.

WIRE's scale path is Postgres + pgvector (HNSW-indexed SQL KNN). Lite mode
(SQLite — zero-infra local dev and free-tier Hugging Face Spaces) gets the
same behaviour with numpy doing the cosine math in-process. Small corpora
(<10k rows) don't need an ANN index anyway.
"""

from collections.abc import Sequence
from typing import Any, TypeVar

import numpy as np
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


def is_postgres(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bool(bind is not None and bind.dialect.name == "postgresql")


def cosine_sim(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


async def knn(
    session: AsyncSession,
    model: type[T],
    embedding_attr: Any,
    query_vec: Sequence[float],
    *,
    limit: int,
    base_query: Select[tuple[T]] | None = None,
) -> list[tuple[T, float]]:
    """Nearest rows by cosine similarity → [(row, similarity), …] best-first.

    Postgres: one indexed SQL query. SQLite: fetch candidates (bounded by the
    base query) and rank in numpy.
    """
    q = base_query if base_query is not None else select(model)
    if is_postgres(session):
        rows = (
            await session.execute(
                q.add_columns(embedding_attr.cosine_distance(list(query_vec)).label("dist"))
                .order_by(embedding_attr.cosine_distance(list(query_vec)))
                .limit(limit)
            )
        ).all()
        return [(row[0], 1.0 - float(row.dist)) for row in rows]

    candidates = (await session.execute(q.limit(5000))).scalars().all()
    scored: list[tuple[T, float]] = []
    for row in candidates:
        vec = getattr(row, embedding_attr.key, None)
        if vec is None:
            continue
        scored.append((row, cosine_sim(query_vec, vec)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
