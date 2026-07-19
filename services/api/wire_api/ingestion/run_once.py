"""`make ingest-once` — run every active source once, then the corpus
pipeline, from the CLI. Populates raw_item against real endpoints; running
it twice adds zero duplicate rows (content-hash dedup)."""

import asyncio

from sqlalchemy import select

from wire_api.corpus.pipeline import run_corpus_cycle
from wire_api.db import session_scope
from wire_api.ingestion.runner import ingest_source
from wire_api.logging import configure_logging, get_logger
from wire_api.models import Source

log = get_logger(__name__)


async def run() -> None:
    async with session_scope() as session:
        sources = (
            (await session.execute(select(Source).where(Source.is_active.is_(True))))
            .scalars()
            .all()
        )
        if not sources:
            log.warning("ingest.no_sources", hint="run `make seed` or add sources via the API")
            return
        totals = {"items_fetched": 0, "items_new": 0}
        for source in sources:
            try:
                metrics = await ingest_source(session, source)
                totals["items_fetched"] += int(metrics["items_fetched"])
                totals["items_new"] += int(metrics["items_new"])
            except Exception as exc:  # noqa: BLE001 — one bad source never stops the run
                log.error("ingest.source_failed", source=source.name, error=str(exc))
        log.info("ingest.totals", **totals)

    await run_corpus_cycle()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
