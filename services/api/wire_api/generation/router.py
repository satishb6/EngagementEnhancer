"""Generation endpoints: the contact sheet, picks, video requests, job states.

This router is the ONLY entry point to video generation in the codebase.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from wire_api.auth.deps import DB, CurrentEntitlement, CurrentUser
from wire_api.billing.credits import InsufficientCredits, PRICE_BY_CONTENT_TYPE
from wire_api.generation.tiers import SelectionCapExceeded, TierViolation
from wire_api.generation.video import (
    ConfirmationRequired,
    approve_storyboard,
    request_video,
)
from wire_api.learning.format_loop import record_impression, record_pick
from wire_api.models import (
    Artifact,
    Briefing,
    Cluster,
    ContentType,
    GenerationJob,
    Take,
)

router = APIRouter(tags=["generation"])


def _artifact_json(a: Artifact) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "content_type": a.content_type.value,
        "variant_index": a.variant_index,
        "text_content": a.text_content,
        "storage_uri": a.storage_uri,
        "width": a.width,
        "height": a.height,
        "duration_ms": a.duration_ms,
        "meta": a.meta,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/takes/{take_id}/sheet")
async def contact_sheet(
    take_id: uuid.UUID, user: CurrentUser, ent: CurrentEntitlement, session: DB
) -> dict[str, Any]:
    """Everything the contact sheet renders: finished frames per content type,
    running jobs, and the not-yet-generated video frames with credit costs."""
    take = (
        await session.execute(
            select(Take).where(Take.id == take_id, Take.user_id == user.id)
        )
    ).scalar_one_or_none()
    if take is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Take not found.")

    jobs = (
        (
            await session.execute(
                select(GenerationJob).where(GenerationJob.take_id == take.id)
            )
        )
        .scalars()
        .all()
    )
    artifacts = (
        (
            await session.execute(
                select(Artifact)
                .where(Artifact.job_id.in_([j.id for j in jobs] or [uuid.uuid4()]))
                .order_by(Artifact.content_type, Artifact.variant_index)
            )
        )
        .scalars()
        .all()
    )

    region = (
        await session.execute(
            select(Cluster.region_key)
            .join(Briefing, Briefing.cluster_id == Cluster.id)
            .where(Briefing.id == take.briefing_id)
        )
    ).scalar_one_or_none() or ""
    # every render on the sheet is an impression for the format loop
    for a in artifacts:
        await record_impression(session, user.id, region, a.content_type.value, "any")
    await session.commit()

    video_offers = []
    if ent.can_video:
        video_offers = [
            {"content_type": "video_short", "credits": int(PRICE_BY_CONTENT_TYPE["video_short"]),
             "max_duration_s": 30, "gated": False},
            {"content_type": "video_long", "credits": int(PRICE_BY_CONTENT_TYPE["video_long"]),
             "max_duration_s": 180, "gated": True},
        ]

    return {
        "take_id": str(take.id),
        "artifacts": [_artifact_json(a) for a in artifacts],
        "jobs": [
            {"id": str(j.id), "content_type": j.content_type.value, "state": j.state.value,
             "variant_index": j.variant_index, "cost_estimate_cents": j.cost_estimate_cents,
             "cost_actual_cents": j.cost_actual_cents, "error": j.error,
             "storyboard": j.params.get("storyboard") if j.params else None,
             "awaiting_approval": bool(
                 j.params.get("storyboard") and not j.params.get("approved")
             ) if j.params else False}
            for j in jobs
        ],
        "video_offers": video_offers,
    }


class PickIn(BaseModel):
    artifact_id: uuid.UUID
    platform: str = Field(default="x", max_length=16)


@router.post("/sheet/pick")
async def pick_frame(body: PickIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    """The grease-pencil circle: a pick, recorded for the format loop."""
    artifact = (
        await session.execute(
            select(Artifact).where(
                Artifact.id == body.artifact_id, Artifact.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Frame not found.")
    job = (
        await session.execute(select(GenerationJob).where(GenerationJob.id == artifact.job_id))
    ).scalar_one()
    take = (
        await session.execute(select(Take).where(Take.id == job.take_id))
    ).scalar_one_or_none()
    region = ""
    if take is not None:
        region = (
            await session.execute(
                select(Cluster.region_key)
                .join(Briefing, Briefing.cluster_id == Cluster.id)
                .where(Briefing.id == take.briefing_id)
            )
        ).scalar_one_or_none() or ""
    await record_pick(session, user.id, region, artifact.content_type.value,
                      body.platform, trigger_id=artifact.id)
    await session.commit()
    return {"picked": str(artifact.id), "platform": body.platform}


class VideoIn(BaseModel):
    take_id: uuid.UUID
    long_form: bool = False
    duration_s: int = Field(ge=5, le=180, default=20)
    confirm_credits: int | None = None


@router.post("/generate/video", status_code=status.HTTP_202_ACCEPTED)
async def generate_video(body: VideoIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    """The explicit user action the lazy-generation rule requires."""
    try:
        job = await request_video(
            session, user, body.take_id,
            long_form=body.long_form, duration_s=body.duration_s,
            confirm_credits=body.confirm_credits,
        )
        await session.commit()
    except ConfirmationRequired as exc:
        return {
            "confirmation_required": True,
            "credits": exc.credits,
            "estimate_cents": exc.estimate_cents,
        }
    except InsufficientCredits as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    except (TierViolation, SelectionCapExceeded) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {
        "job_id": str(job.id),
        "state": job.state.value,
        "cost_estimate_cents": job.cost_estimate_cents,
        "storyboard": job.params.get("storyboard"),
    }


@router.post("/generate/video/{job_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_video_storyboard(
    job_id: uuid.UUID, user: CurrentUser, session: DB
) -> dict[str, Any]:
    try:
        job = await approve_storyboard(session, user, job_id)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"job_id": str(job.id), "state": job.state.value, "shots_started": True}


@router.get("/artifacts")
async def list_artifacts(
    user: CurrentUser, session: DB, limit: int = 60
) -> list[dict[str, Any]]:
    """The user's finished prints, newest first — the library view."""
    rows = (
        (
            await session.execute(
                select(Artifact)
                .where(Artifact.user_id == user.id, Artifact.cold_stored.is_(False))
                .order_by(Artifact.created_at.desc())
                .limit(min(limit, 200))
            )
        )
        .scalars()
        .all()
    )
    return [_artifact_json(a) for a in rows]


@router.get("/jobs")
async def list_jobs(
    user: CurrentUser, session: DB, take_id: uuid.UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    q = select(GenerationJob).where(GenerationJob.user_id == user.id)
    if take_id is not None:
        q = q.where(GenerationJob.take_id == take_id)
    rows = (
        (await session.execute(q.order_by(GenerationJob.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [
        {"id": str(j.id), "content_type": j.content_type.value, "state": j.state.value,
         "tier": j.tier.value, "variant_index": j.variant_index,
         "cost_estimate_cents": j.cost_estimate_cents,
         "cost_actual_cents": j.cost_actual_cents,
         "created_at": j.created_at.isoformat(), "error": j.error}
        for j in rows
    ]
