"""Retention: full payloads for 7 days, then drop prompt/response text and
keep metrics indefinitely. Prompts and responses are the expensive part."""

from datetime import timedelta

from sqlalchemy import text

from wire_api.db import session_scope
from wire_api.logging import get_logger
from wire_api.models.base import utcnow
from wire_api.settings import get_settings

log = get_logger(__name__)

# metric keys survive the strip; everything else in the payload goes
KEEP_KEYS = [
    "provider", "model", "input_tokens", "output_tokens", "cost_cents",
    "items_fetched", "items_new", "quota_consumed", "batch_size", "count",
    "estimate_cents", "actual_cents", "word_count", "variant_index",
]

_STRIP_SQL = text(
    """
    UPDATE pipeline_event
    SET payload = (
        SELECT coalesce(jsonb_object_agg(key, value), '{}'::jsonb)
        FROM jsonb_each(payload)
        WHERE key = ANY(:keep)
    ),
    payload_stripped = true
    WHERE created_at < :cutoff AND payload_stripped = false
    """
)


async def strip_old_payloads() -> int:
    cutoff = utcnow() - timedelta(days=get_settings().trace_full_payload_days)
    async with session_scope() as s:
        from wire_api.dbcompat import is_postgres

        if is_postgres(s):
            result = await s.execute(_STRIP_SQL, {"keep": KEEP_KEYS, "cutoff": cutoff})
            stripped = result.rowcount or 0
        else:
            from sqlalchemy import select

            from wire_api.models import PipelineEvent

            rows = (
                (
                    await s.execute(
                        select(PipelineEvent).where(
                            PipelineEvent.created_at < cutoff,
                            PipelineEvent.payload_stripped.is_(False),
                        ).limit(5000)
                    )
                )
                .scalars()
                .all()
            )
            for event in rows:
                event.payload = {k: v for k, v in (event.payload or {}).items()
                                 if k in KEEP_KEYS}
                event.payload_stripped = True
            stripped = len(rows)
    log.info("trace.retention", stripped=stripped)
    return stripped
