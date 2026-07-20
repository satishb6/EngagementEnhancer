"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from wire_api import __version__
from wire_api.db import dispose_engine, get_engine
from wire_api.logging import configure_logging, get_logger
from wire_api.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    log.info("wire_api.start", version=__version__, env=settings.wire_env,
             lite_mode=not settings.redis_url)
    tasks = []
    if settings.embedded_worker:
        from wire_api.embedded import start_embedded_loops

        tasks = start_embedded_loops()
    yield
    for task in tasks:
        task.cancel()
    await dispose_engine()
    log.info("wire_api.stop")


app = FastAPI(title="WIRE API", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost(:\d+)?|.*\.vercel\.app|.*\.hf\.space)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_engine_middleware(request, call_next):  # type: ignore[no-untyped-def]
    """Frontend BYOK: keys arrive per request, live for the request only."""
    from wire_api.providers.request_keys import clear_request_engine, set_request_engine

    set_request_engine(
        request.headers.get("x-wire-keys"),
        request.headers.get("x-wire-provider"),
        request.headers.get("x-wire-model"),
    )
    try:
        return await call_next(request)
    finally:
        clear_request_engine()


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness + a cheap DB round-trip so 'healthy' means something."""
    status = "ok"
    db = "ok"
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — health must never raise
        db = "unreachable"
        status = "degraded"
    return {"status": status, "db": db, "version": __version__}


def _register_routers() -> None:
    # Imported lazily so `main` stays importable before later phases exist.
    from wire_api.auth.router import router as auth_router
    from wire_api.billing.router import router as billing_router
    from wire_api.feed.router import router as feed_router
    from wire_api.generation.router import router as generation_router
    from wire_api.graph.router import router as graph_router
    from wire_api.protocols.router import router as protocols_router
    from wire_api.publishing.router import router as publishing_router
    from wire_api.system.router import router as system_router
    from wire_api.takes.router import router as takes_router
    from wire_api.tracing.router import router as tracing_router

    app.include_router(auth_router)
    app.include_router(feed_router)
    app.include_router(takes_router)
    app.include_router(generation_router)
    app.include_router(billing_router)
    app.include_router(publishing_router)
    app.include_router(tracing_router)
    app.include_router(graph_router)
    app.include_router(protocols_router)
    app.include_router(system_router)


_register_routers()
