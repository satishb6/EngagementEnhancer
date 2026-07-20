"""Shared fixtures. Integration tests get a real Postgres.

Resolution order for the test database:
1. TEST_DATABASE_URL env var (CI provides a pgvector service container)
2. testcontainers (needs Docker locally)
Tests marked `integration` are skipped when neither is available.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wire_api.models import Base


def _test_db_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if url and "test" in url:
        return url
    if url and os.environ.get("CI"):
        return url
    try:
        from testcontainers.postgres import PostgresContainer  # noqa: F401

        import docker

        docker.from_env().ping()
        return "testcontainers"
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    resolved = _test_db_url()
    if resolved is None:
        pytest.skip("integration test: no TEST_DATABASE_URL and no Docker for testcontainers")
    if resolved == "testcontainers":
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("pgvector/pgvector:pg16") as pg:
            url = pg.get_connection_url().replace("psycopg2", "asyncpg")
            yield url
    else:
        yield resolved


@pytest.fixture()
async def db(pg_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(pg_url, poolclass=None)
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    # fresh schema per test — cheap at this scale, hermetic forever
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def make_user_kwargs(email: str | None = None) -> dict[str, object]:
    return {
        "email": email or f"u{uuid.uuid4().hex[:10]}@wire.test",
        "password_hash": "scrypt$x$y",
        "display_name": "Test",
    }
