"""Take capture: the user's opinion, typed or spoken, plus the
friction-killer — three suggested stances they can tap and edit."""

import difflib
import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from wire_api.agents.prompts import PROVOCATEUR
from wire_api.auth.deps import DB, CurrentUser
from wire_api.learning.voice import (
    similar_takes,
    style_constraints,
    update_style_profile,
)
from wire_api.models import Briefing, StyleProfile, Take, TakeSource
from wire_api.models.tracing import Stage
from wire_api.providers import Capability, Message, get_router
from wire_api.tracing.traced import traced_span

router = APIRouter(prefix="/take", tags=["takes"])

# a suggestion edited past this character-diff ratio flips to AUTHORED — the
# UI's Redaction grade animation and the voice model both key off it
AUTHORED_THRESHOLD = 0.30

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _edit_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, a, b).ratio()


class TakeIn(BaseModel):
    briefing_id: uuid.UUID
    feed_item_id: uuid.UUID | None = None
    text: str = Field(min_length=1, max_length=2000)
    # what the user started from, if they tapped a suggestion
    suggested_text: str = ""
    stance: str = ""


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_take(body: TakeIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == body.briefing_id))
    ).scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found.")

    existing = (
        await session.execute(
            select(Take).where(Take.user_id == user.id, Take.briefing_id == body.briefing_id)
        )
    ).scalar_one_or_none()

    ratio = _edit_ratio(body.suggested_text, body.text) if body.suggested_text else 1.0
    source = TakeSource.AUTHORED if ratio >= AUTHORED_THRESHOLD else TakeSource.SUGGESTED

    router_ = get_router()
    embedding: list[float] | None = None
    try:
        binding = await router_.resolve(Capability.EMBEDDING, user, session)
        embedding = (await binding.provider.embed([body.text])).vectors[0]
    except Exception:  # noqa: BLE001 — a take must never be lost to an embed failure
        embedding = None

    if existing is None:
        take = Take(
            user_id=user.id, briefing_id=body.briefing_id, feed_item_id=body.feed_item_id,
            text_content=body.text, stance=body.stance, source=source,
            suggested_text=body.suggested_text, edit_distance_ratio=ratio,
            embedding=embedding,
        )
        session.add(take)
        await session.flush()
    else:
        existing.text_content = body.text
        existing.stance = body.stance
        existing.source = source
        existing.suggested_text = body.suggested_text
        existing.edit_distance_ratio = ratio
        if embedding is not None:
            existing.embedding = embedding
        take = existing

    if source is TakeSource.AUTHORED:
        await update_style_profile(session, user.id, take)

    # kick eager generation (text variants + images + gifs) — async, never here
    from wire_api.generation.orchestrator import enqueue_eager_generation

    job_ids = await enqueue_eager_generation(session, user, take)
    await session.commit()

    return {
        "take_id": str(take.id),
        "source": source.value,
        "edit_distance_ratio": round(ratio, 3),
        "generation_job_ids": job_ids,
    }


@router.post("/audio", status_code=status.HTTP_201_CREATED)
async def create_take_from_audio(
    user: CurrentUser,
    session: DB,
    briefing_id: uuid.UUID = Form(...),
    audio: UploadFile = File(...),
) -> dict[str, Any]:
    """Voice take: transcribe, store both, return transcript for confirmation."""
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    ).scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found.")

    data = await audio.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio over 25MB.")

    router_ = get_router()
    async with traced_span(
        session, Stage.GENERATE, entity_type="transcription", user_id=user.id
    ) as span:
        binding = await router_.resolve(Capability.AUDIO, user, session)
        result = await binding.provider.transcribe(
            data, content_type=audio.content_type or "audio/wav"
        )
        span.payload.update({
            "provider": result.meta.provider_id, "model": result.meta.model_id,
            "cost_cents": result.meta.cost_cents, "duration_s": result.duration_s,
        })

    await session.commit()
    return {
        "transcript": result.text,
        "duration_s": result.duration_s,
        "next": "confirm via POST /take with the edited transcript",
    }


class SuggestIn(BaseModel):
    briefing_id: uuid.UUID


@router.post("/suggest")
async def suggest_takes(body: SuggestIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    """Three candidate takes with genuinely different stances. Every one is
    marked source:'suggested'; editing past 30% flips it to 'authored'."""
    briefing = (
        await session.execute(select(Briefing).where(Briefing.id == body.briefing_id))
    ).scalar_one_or_none()
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found.")

    profile = (
        await session.execute(select(StyleProfile).where(StyleProfile.user_id == user.id))
    ).scalar_one_or_none()

    few_shot: list[str] = []
    if briefing.embedding is not None:
        past = await similar_takes(session, user.id, briefing.embedding, k=5)
        few_shot = [t.text_content for t in past]

    stance_history: dict[str, float] = dict(profile.stance_distribution) if profile else {}

    payload = {
        "briefing": {"headline": briefing.headline, "body": briefing.body},
        "style_profile": style_constraints(profile),
        "similar_past_takes": few_shot,
        "stance_history": stance_history,
    }

    router_ = get_router()
    async with traced_span(
        session, Stage.GENERATE, entity_type="suggestion",
        entity_id=str(briefing.id), user_id=user.id,
    ) as span:
        binding = await router_.resolve(Capability.TEXT, user, session)
        result = await binding.provider.complete(
            [Message("system", PROVOCATEUR),
             Message("user", json.dumps(payload, ensure_ascii=False))],
            max_tokens=500,
        )
        span.payload.update({
            "provider": binding.provider_id, "model": result.meta.model_id,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            "cost_cents": result.meta.cost_cents,
            "prompt": json.dumps(payload)[:4000], "response": result.text[:4000],
        })

    match = _JSON_ARRAY_RE.search(result.text)
    suggestions: list[dict[str, str]] = []
    if match:
        try:
            raw = json.loads(match.group())
            suggestions = [
                {"stance": str(s.get("stance", "SKEPTICAL")).upper(),
                 "text": str(s.get("text", "")).strip(),
                 "source": "suggested"}
                for s in raw[:3]
                if s.get("text")
            ]
        except json.JSONDecodeError:
            suggestions = []

    if len(suggestions) < 3:
        # cold-start fallback: generic but well-written stances, never empty
        suggestions = (suggestions + [
            {"stance": "SKEPTICAL", "source": "suggested",
             "text": "I'd wait before drawing conclusions here — the incentives "
                     "behind this announcement matter more than the announcement."},
            {"stance": "OPTIMISTIC", "source": "suggested",
             "text": "This is quietly a bigger deal than the coverage suggests, "
                     "and I think we look back at it as a turning point."},
            {"stance": "CONTRARIAN", "source": "suggested",
             "text": "Everyone's reading this the same way, which is usually a "
                     "sign the consensus is about to be wrong."},
        ])[:3]

    await session.commit()
    return {"briefing_id": str(briefing.id), "suggestions": suggestions}
