"""Video generation — ON_DEMAND (short) and GATED (long).

The ONLY caller of request_video is the generation router, i.e. a request
handler acting on an explicit user action that already passed an
entitlement check. Background tasks may poll running jobs; they may never
create one. tests/test_cost_guardrails.py enforces this by inspection.
"""

import json
import math
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.agents.prompts import DIRECTOR
from wire_api.billing.credits import (
    PRICE_BY_CONTENT_TYPE,
    commit_reservation,
    refund_reservation,
    reserve,
)
from wire_api.db import session_scope
from wire_api.generation.storage import mirror_url
from wire_api.generation.tiers import TIER_BY_CONTENT_TYPE, artifact_ttl, assert_tier_allowed
from wire_api.logging import get_logger
from wire_api.models import (
    Artifact,
    Briefing,
    ContentType,
    Entitlement,
    GenerationJob,
    JobState,
    Take,
    Tier,
    User,
)
from wire_api.models.base import utcnow
from wire_api.models.tracing import Stage
from wire_api.providers import Capability, Message, estimate_cost, get_router
from wire_api.tracing.traced import traced_span

log = get_logger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SHORT_MAX_S = 30
LONG_MAX_S = 180


class ConfirmationRequired(RuntimeError):
    """GATED jobs need the client to echo the shown cost back."""

    def __init__(self, estimate_cents: int, credits: int) -> None:
        self.estimate_cents = estimate_cents
        self.credits = credits
        super().__init__(
            f"Long-form video costs ~{credits} credits (${estimate_cents / 100:.2f} COGS). "
            "Repeat the request with confirm_credits set to that figure."
        )


async def request_video(
    session: AsyncSession,
    user: User,
    take_id: uuid.UUID,
    *,
    long_form: bool,
    duration_s: int,
    confirm_credits: int | None = None,
) -> GenerationJob:
    """Create (and start) a user-initiated video job. Raises on any gate."""
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one()
    take = (
        await session.execute(
            select(Take).where(Take.id == take_id, Take.user_id == user.id)
        )
    ).scalar_one()

    content_type = ContentType.VIDEO_LONG if long_form else ContentType.VIDEO_SHORT
    duration_s = min(duration_s, LONG_MAX_S if long_form else SHORT_MAX_S)
    estimate_cents = math.ceil(estimate_cost(Capability.VIDEO, {"duration_s": duration_s}))
    credits = int(PRICE_BY_CONTENT_TYPE[content_type.value])

    if long_form and confirm_credits != credits:
        # the confirmation dialog shows this figure; the client echoes it back
        raise ConfirmationRequired(estimate_cents, credits)

    job = GenerationJob(
        user_id=user.id,
        take_id=take.id,
        state=JobState.QUEUED,
        content_type=content_type,
        tier=TIER_BY_CONTENT_TYPE[content_type],
        cost_estimate_cents=estimate_cents,
        idempotency_key=f"video:{take.id}:{content_type}:{utcnow().strftime('%Y%m%d%H')}",
        user_initiated=True,
        params={"duration_s": duration_s},
    )
    existing = (
        await session.execute(
            select(GenerationJob).where(GenerationJob.idempotency_key == job.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    assert_tier_allowed(job, ent)
    session.add(job)
    await session.flush()

    if ent.tier is Tier.PRO:
        await reserve(session, user.id, credits, job.id)
        job.credits_charged = credits

    # long form: storyboard first — stills the user approves BEFORE any
    # image-to-video renders
    if long_form:
        await _storyboard(session, user, job, take)
        job.state = JobState.RUNNING  # awaiting approval; no renders yet
        return job

    # short form: single i2v pass, kicked off now, advanced by the poller
    await _start_short_video(session, user, job, take)
    return job


async def _storyboard(
    session: AsyncSession, user: User, job: GenerationJob, take: Take
) -> None:
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == take.briefing_id))
    ).scalar_one()
    router = get_router()
    async with traced_span(
        session, Stage.GENERATE, entity_type="storyboard",
        entity_id=str(job.id), user_id=user.id,
    ) as span:
        binding = await router.resolve(Capability.TEXT, user, session)
        result = await binding.provider.complete(
            [Message("system", DIRECTOR),
             Message("user", json.dumps({
                 "take": take.text_content,
                 "briefing": {"headline": briefing.headline, "body": briefing.body},
                 "form": "long", "max_duration_s": job.params.get("duration_s", LONG_MAX_S),
             }))],
            max_tokens=1500,
        )
        span.payload.update({
            "provider": binding.provider_id, "model": result.meta.model_id,
            "cost_cents": result.meta.cost_cents,
        })
    match = _JSON_RE.search(result.text)
    if not match:
        raise RuntimeError("Director returned no storyboard JSON")
    storyboard = json.loads(match.group())
    job.params = {**job.params, "storyboard": storyboard, "approved": False}

    # render the storyboard stills for approval
    image_binding = await router.resolve(Capability.IMAGE, user, session)
    for shot in storyboard.get("shots", [])[:12]:
        stills = await image_binding.provider.generate(
            str(shot["image_prompt"]), size="1280x720", n=1
        )
        if stills:
            uri = await mirror_url(stills[0].url, ".png") if stills[0].url else stills[0].path
            session.add(Artifact(
                job_id=job.id, user_id=user.id, content_type=ContentType.IMAGE,
                variant_index=int(shot.get("index", 0)),
                storage_uri=uri, width=1280, height=720,
                meta={"role": "storyboard_frame", "shot": shot},
                expires_at=utcnow() + artifact_ttl(
                    (await session.execute(
                        select(Entitlement).where(Entitlement.user_id == user.id)
                    )).scalar_one()
                ),
            ))


async def approve_storyboard(
    session: AsyncSession, user: User, job_id: uuid.UUID
) -> GenerationJob:
    """User approved the frames: start image-to-video per shot."""
    job = (
        await session.execute(
            select(GenerationJob).where(
                GenerationJob.id == job_id, GenerationJob.user_id == user.id
            )
        )
    ).scalar_one()
    if not job.params.get("storyboard"):
        raise RuntimeError("No storyboard on this job.")
    job.params = {**job.params, "approved": True, "shot_refs": []}

    router = get_router()
    binding = await router.resolve(Capability.VIDEO, user, session)
    frames = (
        (
            await session.execute(
                select(Artifact).where(
                    Artifact.job_id == job.id,
                    Artifact.content_type == ContentType.IMAGE,
                ).order_by(Artifact.variant_index)
            )
        )
        .scalars()
        .all()
    )
    shot_refs: list[dict[str, Any]] = []
    for frame in frames:
        shot = frame.meta.get("shot", {})
        video_job = await binding.provider.generate(
            str(shot.get("motion_prompt", "subtle camera drift")),
            init_image=frame.storage_uri,
            duration_s=int(float(shot.get("duration_s", 4))),
        )
        shot_refs.append({"job_ref": video_job.job_ref, "index": frame.variant_index,
                          "status": "running"})
    job.params = {**job.params, "shot_refs": shot_refs, "provider_id": binding.provider_id}
    return job


async def _start_short_video(
    session: AsyncSession, user: User, job: GenerationJob, take: Take
) -> None:
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == take.briefing_id))
    ).scalar_one()
    # use the first eager image as init frame if it exists
    init = (
        await session.execute(
            select(Artifact)
            .join(GenerationJob, GenerationJob.id == Artifact.job_id)
            .where(GenerationJob.take_id == take.id,
                   Artifact.content_type == ContentType.IMAGE)
            .order_by(Artifact.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()

    router = get_router()
    binding = await router.resolve(Capability.VIDEO, user, session)
    prompt = (
        f"Short social video about: {briefing.headline}. "
        f"Angle: {take.text_content[:200]}. Dynamic but not chaotic."
    )
    video_job = await binding.provider.generate(
        prompt,
        init_image=init.storage_uri if init else None,
        duration_s=int(job.params.get("duration_s", 20)),
    )
    job.state = JobState.RUNNING
    job.started_at = utcnow()
    job.provider_id = binding.provider_id
    job.params = {**job.params, "job_ref": video_job.job_ref}


async def poll_running_video_jobs() -> int:
    """Beat task: advance running video jobs. Creates none — ever."""
    advanced = 0
    async with session_scope() as session:
        jobs = (
            (
                await session.execute(
                    select(GenerationJob).where(
                        GenerationJob.state == JobState.RUNNING,
                        GenerationJob.content_type.in_(
                            [ContentType.VIDEO_SHORT, ContentType.VIDEO_LONG]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            try:
                if job.content_type is ContentType.VIDEO_SHORT:
                    advanced += await _poll_short(session, job)
                else:
                    advanced += await _poll_long(session, job)
            except Exception as exc:  # noqa: BLE001
                log.warning("video.poll_failed", job_id=str(job.id), error=str(exc))
    return advanced


async def _poll_short(session: AsyncSession, job: GenerationJob) -> int:
    job_ref = str(job.params.get("job_ref", ""))
    if not job_ref:
        return 0
    user = (
        await session.execute(select(User).where(User.id == job.user_id))
    ).scalar_one()
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == job.user_id))
    ).scalar_one()
    router = get_router()
    binding = await router.resolve(Capability.VIDEO, user, session)
    status = await binding.provider.poll(job_ref)
    if status.status == "succeeded":
        uri = await mirror_url(status.url, ".mp4") if status.url else ""
        session.add(Artifact(
            job_id=job.id, user_id=job.user_id, content_type=job.content_type,
            storage_uri=uri, duration_ms=int(job.params.get("duration_s", 20)) * 1000,
            meta={"provider": binding.provider_id},
            expires_at=utcnow() + artifact_ttl(ent),
        ))
        job.state = JobState.SUCCEEDED
        job.finished_at = utcnow()
        job.cost_actual_cents = job.cost_estimate_cents
        if ent.tier is Tier.PRO and job.credits_charged:
            await commit_reservation(session, job.user_id, job.id, job.credits_charged)
        return 1
    if status.status == "failed":
        job.state = JobState.FAILED
        job.finished_at = utcnow()
        job.error = {"type": "ProviderFailure", "message": "video render failed"}
        if ent.tier is Tier.PRO and job.credits_charged:
            await refund_reservation(session, job.user_id, job.id)
        return 1
    return 0


async def _poll_long(session: AsyncSession, job: GenerationJob) -> int:
    if not job.params.get("approved"):
        return 0
    shot_refs: list[dict[str, Any]] = list(job.params.get("shot_refs", []))
    if not shot_refs:
        return 0
    user = (
        await session.execute(select(User).where(User.id == job.user_id))
    ).scalar_one()
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == job.user_id))
    ).scalar_one()
    router = get_router()
    binding = await router.resolve(Capability.VIDEO, user, session)

    changed = False
    for shot in shot_refs:
        if shot["status"] != "running":
            continue
        status = await binding.provider.poll(str(shot["job_ref"]))
        if status.status == "succeeded":
            shot["status"] = "succeeded"
            shot["url"] = status.url
            changed = True
        elif status.status == "failed":
            shot["status"] = "failed"
            changed = True
    if changed:
        job.params = {**job.params, "shot_refs": shot_refs}

    if all(s["status"] != "running" for s in shot_refs):
        succeeded = [s for s in sorted(shot_refs, key=lambda s: s["index"])
                     if s["status"] == "succeeded"]
        if not succeeded:
            job.state = JobState.FAILED
            job.finished_at = utcnow()
            if ent.tier is Tier.PRO and job.credits_charged:
                await refund_reservation(session, job.user_id, job.id)
            return 1
        # download shots, concat with ffmpeg, store the film
        import tempfile
        from pathlib import Path

        from wire_api.generation.gif import concat_videos
        from wire_api.generation.storage import save_bytes

        import httpx

        with tempfile.TemporaryDirectory() as tmp:
            paths: list[Path] = []
            async with httpx.AsyncClient(timeout=600) as client:
                for i, shot in enumerate(succeeded):
                    resp = await client.get(str(shot["url"]))
                    resp.raise_for_status()
                    p = Path(tmp) / f"shot{i}.mp4"
                    p.write_bytes(resp.content)
                    paths.append(p)
            out = Path(tmp) / "film.mp4"
            await concat_videos(paths, out)
            uri = await save_bytes(out.read_bytes(), ".mp4")

        session.add(Artifact(
            job_id=job.id, user_id=job.user_id, content_type=job.content_type,
            storage_uri=uri,
            meta={"provider": binding.provider_id, "shots": len(succeeded)},
            expires_at=utcnow() + artifact_ttl(ent),
        ))
        job.state = JobState.PARTIAL if len(succeeded) < len(shot_refs) else JobState.SUCCEEDED
        job.finished_at = utcnow()
        job.cost_actual_cents = job.cost_estimate_cents
        if ent.tier is Tier.PRO and job.credits_charged:
            await commit_reservation(session, job.user_id, job.id, job.credits_charged)
        return 1
    return 0
