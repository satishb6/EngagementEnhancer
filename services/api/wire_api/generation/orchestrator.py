"""Generation orchestration.

Flow: the take endpoint calls enqueue_eager_generation() (creates job rows
with persisted cost estimates + credit reservations, then dispatches one
Celery task). Workers call execute_jobs(). Partial success is normal: if
variant 2 of 3 fails, 1 and 3 ship and the set reads partial — never fail
the whole set.
"""

import json
import math
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.agents.prompts import COMPOSER
from wire_api.billing.credits import (
    PRICE_BY_CONTENT_TYPE,
    InsufficientCredits,
    commit_reservation,
    refund_reservation,
    reserve,
)
from wire_api.db import session_scope
from wire_api.generation.gif import ken_burns_gif
from wire_api.generation.storage import mirror_url, save_bytes
from wire_api.generation.tiers import (
    TIER_BY_CONTENT_TYPE,
    assert_selection_allowed,
    assert_tier_allowed,
    artifact_ttl,
)
from wire_api.logging import get_logger
from wire_api.models import (
    Artifact,
    Briefing,
    ContentType,
    Entitlement,
    GenerationJob,
    JobState,
    StyleProfile,
    Take,
    Tier,
    User,
)
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.providers import Capability, Message, estimate_cost, get_router
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

EAGER_TYPES = [ContentType.TEXT, ContentType.IMAGE, ContentType.GIF]
COST_ALERT_RATIO = 1.20


async def enqueue_eager_generation(
    session: AsyncSession, user: User, take: Take
) -> list[str]:
    """Create EAGER job rows (estimates persisted, credits reserved) and hand
    them to the worker. Free tier gets variant_count=1 and its daily selection
    cap — enforced here, server-side, not by the client."""
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one()
    await assert_selection_allowed(session, user, ent, take)

    job_ids: list[str] = []
    for content_type in EAGER_TYPES:
        variants = ent.variant_count if content_type is not ContentType.GIF else 1
        if ent.tier is Tier.FREE and content_type is ContentType.IMAGE:
            variants = 1
        for variant_index in range(variants):
            capability = {
                ContentType.TEXT: Capability.TEXT,
                ContentType.IMAGE: Capability.IMAGE,
                ContentType.GIF: Capability.IMAGE,  # source still; synthesis is free
            }[content_type]
            estimate = (
                0.0 if content_type is ContentType.GIF
                else estimate_cost(capability, {"n": 1})
            )
            job = GenerationJob(
                user_id=user.id,
                take_id=take.id,
                state=JobState.QUEUED,
                content_type=content_type,
                tier=TIER_BY_CONTENT_TYPE[content_type],
                variant_index=variant_index,
                # estimates round UP to whole cents — surprises should favour the user
                cost_estimate_cents=math.ceil(estimate) if estimate > 0 else 0,
                idempotency_key=f"eager:{take.id}:{content_type}:{variant_index}",
                user_initiated=True,  # the take submission is the human action
                params={},
            )
            # idempotent enqueue: a retried request reuses existing jobs
            existing = (
                await session.execute(
                    select(GenerationJob).where(
                        GenerationJob.idempotency_key == job.idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                job_ids.append(str(existing.id))
                continue
            session.add(job)
            await session.flush()

            # credits: only the platform-billed pro tier pays per generation
            if ent.tier is Tier.PRO:
                credits = int(PRICE_BY_CONTENT_TYPE[content_type.value])
                try:
                    await reserve(session, user.id, credits, job.id)
                    job.credits_charged = credits
                except InsufficientCredits:
                    job.state = JobState.CANCELLED
                    job.error = {"type": "InsufficientCredits",
                                 "message": "Not enough credits for this variant."}
                    continue
            job_ids.append(str(job.id))

    if job_ids:
        from wire_api.embedded import dispatch_generation

        dispatch_generation(job_ids)
    return job_ids


async def execute_jobs(job_ids: list[str]) -> dict[str, Any]:
    """Worker entrypoint. Every job passes the tier gate before running."""
    results = {"succeeded": 0, "failed": 0}
    for job_id in job_ids:
        async with session_scope() as session:
            job = (
                await session.execute(
                    select(GenerationJob).where(GenerationJob.id == uuid.UUID(job_id))
                )
            ).scalar_one_or_none()
            if job is None or job.state not in (JobState.QUEUED, JobState.RUNNING):
                continue
            ent = (
                await session.execute(
                    select(Entitlement).where(Entitlement.user_id == job.user_id)
                )
            ).scalar_one()
            try:
                assert_tier_allowed(job, ent)
                job.state = JobState.RUNNING
                job.started_at = utcnow()
                await session.flush()
                await _run_single_job(session, job, ent)
                job.state = JobState.SUCCEEDED
                job.finished_at = utcnow()
                if ent.tier is Tier.PRO and job.credits_charged:
                    await commit_reservation(session, job.user_id, job.id, job.credits_charged)
                results["succeeded"] += 1
            except Exception as exc:  # noqa: BLE001 — partial success is normal
                job.state = JobState.FAILED
                job.finished_at = utcnow()
                job.error = {"type": type(exc).__name__, "message": str(exc)[:1000]}
                if ent.tier is Tier.PRO and job.credits_charged:
                    await refund_reservation(session, job.user_id, job.id)
                log.warning("generation.job_failed", job_id=job_id, error=str(exc))
                results["failed"] += 1
    return results


async def _run_single_job(
    session: AsyncSession, job: GenerationJob, ent: Entitlement
) -> None:
    take = (
        await session.execute(select(Take).where(Take.id == job.take_id))
    ).scalar_one()
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == take.briefing_id))
    ).scalar_one()
    user = (
        await session.execute(select(User).where(User.id == job.user_id))
    ).scalar_one()
    router = get_router()
    ttl = artifact_ttl(ent)

    async with traced_span(
        session, Stage.GENERATE,
        entity_type=job.content_type.value, entity_id=str(job.id), user_id=job.user_id,
    ) as span:
        actual_cents = 0.0
        if job.content_type is ContentType.TEXT:
            profile = (
                await session.execute(
                    select(StyleProfile).where(StyleProfile.user_id == job.user_id)
                )
            ).scalar_one_or_none()
            from wire_api.learning.voice import style_constraints

            payload = {
                "briefing": {"headline": briefing.headline, "body": briefing.body,
                             "source_links": briefing.source_links[:2]},
                "take": {"text": take.text_content, "source": take.source.value},
                "style_profile": style_constraints(profile),
                "target_platform": job.target_platform or "x",
                "content_type": "text",
                "variant_index": job.variant_index,
            }
            binding = await router.resolve(Capability.TEXT, user, session)
            result = await binding.provider.complete(
                [Message("system", COMPOSER),
                 Message("user", json.dumps(payload, ensure_ascii=False))],
                max_tokens=700,
            )
            actual_cents = result.meta.cost_cents
            session.add(Artifact(
                job_id=job.id, user_id=job.user_id, content_type=ContentType.TEXT,
                variant_index=job.variant_index, text_content=result.text.strip(),
                meta={"provider": result.meta.provider_id, "model": result.meta.model_id},
                expires_at=utcnow() + ttl,
            ))
            span.payload.update({
                "provider": result.meta.provider_id, "model": result.meta.model_id,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            })

        elif job.content_type is ContentType.IMAGE:
            prompt = _image_prompt(briefing.headline, take.text_content, job.variant_index)
            binding = await router.resolve(Capability.IMAGE, user, session)
            images = await binding.provider.generate(prompt, size="1024x1024", n=1)
            if not images:
                raise RuntimeError("image provider returned nothing")
            img = images[0]
            actual_cents = img.meta.cost_cents
            if img.url.startswith("data:"):
                uri = img.url  # demo placeholder — stored inline
            elif img.url:
                uri = await mirror_url(img.url, ".png")
            else:
                uri = img.path
            session.add(Artifact(
                job_id=job.id, user_id=job.user_id, content_type=ContentType.IMAGE,
                variant_index=job.variant_index, storage_uri=uri,
                width=img.width, height=img.height,
                meta={"provider": img.meta.provider_id, "model": img.meta.model_id,
                      "seed": img.seed, "prompt": prompt},
                expires_at=utcnow() + ttl,
            ))
            span.payload.update({"provider": img.meta.provider_id, "model": img.meta.model_id})

        elif job.content_type is ContentType.GIF:
            # synthesised from a sibling image artifact — zero model cost
            sibling = (
                await session.execute(
                    select(Artifact)
                    .join(GenerationJob, GenerationJob.id == Artifact.job_id)
                    .where(
                        GenerationJob.take_id == job.take_id,
                        Artifact.content_type == ContentType.IMAGE,
                    )
                    .order_by(Artifact.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if sibling is None or not sibling.storage_uri:
                raise RuntimeError("no source image yet for gif synthesis")
            if sibling.storage_uri.startswith("data:"):
                raise RuntimeError(
                    "GIFs need a real rendered image — add a fal.ai key in "
                    "Studio → Engine and regenerate."
                )
            from pathlib import Path

            source = Path(sibling.storage_uri)
            if not source.exists():
                raise RuntimeError("source image not on local disk; gif deferred")
            gif_bytes = await ken_burns_gif(source.read_bytes())
            uri = await save_bytes(gif_bytes, ".gif")
            session.add(Artifact(
                job_id=job.id, user_id=job.user_id, content_type=ContentType.GIF,
                variant_index=job.variant_index, storage_uri=uri,
                duration_ms=3000,
                meta={"synthesis": "ken_burns", "source_artifact": str(sibling.id)},
                expires_at=utcnow() + ttl,
            ))
        else:
            raise RuntimeError(
                f"content_type {job.content_type} does not run through the eager "
                "executor. Video runs only via wire_api.generation.video."
            )

        job.cost_actual_cents = int(round(actual_cents))
        span.payload["cost_cents"] = actual_cents
        span.payload["estimate_cents"] = job.cost_estimate_cents
        if job.cost_estimate_cents and actual_cents > job.cost_estimate_cents * COST_ALERT_RATIO:
            log.error(
                "generation.cost_overrun",
                job_id=str(job.id),
                estimate_cents=job.cost_estimate_cents,
                actual_cents=actual_cents,
            )


def _image_prompt(headline: str, take_text: str, variant: int) -> str:
    styles = [
        "bold editorial illustration, flat colour, strong composition",
        "documentary photography style, natural light, 35mm",
        "minimal conceptual graphic, single striking metaphor",
    ]
    return (
        f"{styles[variant % len(styles)]}. Subject: {headline}. "
        f"Tone informed by this point of view: {take_text[:200]}. "
        "No text, no words, no watermarks, no logos."
    )
