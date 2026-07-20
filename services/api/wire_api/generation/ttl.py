"""Artifact TTL sweep: expired artifacts move to cold storage (metadata kept,
bytes removed locally). Generated media compounds silently otherwise."""

from sqlalchemy import select

from wire_api.db import session_scope
from wire_api.generation.storage import delete_uri
from wire_api.logging import get_logger
from wire_api.models import Artifact
from wire_api.models.base import utcnow

log = get_logger(__name__)


async def sweep_expired_artifacts() -> int:
    swept = 0
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(Artifact).where(
                        Artifact.expires_at < utcnow(),
                        Artifact.cold_stored.is_(False),
                    ).limit(500)
                )
            )
            .scalars()
            .all()
        )
        for artifact in rows:
            if artifact.storage_uri:
                try:
                    await delete_uri(artifact.storage_uri)
                except Exception as exc:  # noqa: BLE001
                    log.warning("ttl.delete_failed", artifact=str(artifact.id), error=str(exc))
                    continue
            artifact.cold_stored = True
            swept += 1
    log.info("ttl.sweep", swept=swept)
    return swept
