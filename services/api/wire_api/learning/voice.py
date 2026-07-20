"""Loop 2 — VOICE. Retrieval-augmented style, no fine-tuning.

Each authored take is stored with its embedding. At generation time we
retrieve the k=5 most semantically similar past takes as few-shot examples
plus a statistical style profile as constraints. Works from take #3, costs
nothing extra, instantly resettable. LoRA is an upgrade path, not a start.
"""

import re
import statistics
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import LearningEvent, StyleProfile, Take, TakeSource

_HEDGES = re.compile(
    r"\b(maybe|perhaps|possibly|i think|i guess|sort of|kind of|arguably|probably)\b",
    re.IGNORECASE,
)
_PROFANITY = re.compile(r"\b(damn|hell|shit|fuck|crap|bullshit)\b", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


async def update_style_profile(
    session: AsyncSession, user_id: uuid.UUID, new_take: Take
) -> StyleProfile:
    """Statistical Stenographer: incremental, weight 0.15 on new evidence.
    The LLM Stenographer refines signature_constructions asynchronously; the
    stats here are always current even with zero model calls."""
    profile = (
        await session.execute(select(StyleProfile).where(StyleProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is None:
        profile = StyleProfile(user_id=user_id)
        session.add(profile)

    text = new_take.text_content
    sentences = _sentences(text)
    lengths = [len(s.split()) for s in sentences] or [0]
    mean = statistics.mean(lengths)
    sd = statistics.stdev(lengths) if len(lengths) > 1 else 0.0
    words = max(len(text.split()), 1)

    alpha = 0.15 if profile.take_count else 1.0
    profile.sentence_length_mean = (1 - alpha) * profile.sentence_length_mean + alpha * mean
    profile.sentence_length_sd = (1 - alpha) * profile.sentence_length_sd + alpha * sd
    profile.hedging_ratio = (
        (1 - alpha) * profile.hedging_ratio + alpha * len(_HEDGES.findall(text)) / words
    )
    profile.question_frequency = (
        (1 - alpha) * profile.question_frequency + alpha * text.count("?") / max(len(sentences), 1)
    )
    profile.profanity = profile.profanity or bool(_PROFANITY.search(text))

    if new_take.stance:
        dist = dict(profile.stance_distribution or {})
        dist[new_take.stance] = dist.get(new_take.stance, 0.0) + 1.0
        total = sum(dist.values())
        profile.stance_distribution = {k: v / total for k, v in dist.items()}

    samples = list(profile.sample_sentences or [])
    for s in sentences[:2]:
        if s not in samples:
            samples.append(s)
    profile.sample_sentences = samples[-12:]

    profile.take_count += 1

    session.add(LearningEvent(
        user_id=user_id, loop="voice", trigger_kind="take", trigger_id=new_take.id,
        detail={"take_count": profile.take_count,
                "sentence_length_mean": round(profile.sentence_length_mean, 2)},
    ))
    return profile


async def similar_takes(
    session: AsyncSession, user_id: uuid.UUID, embedding: list[float], k: int = 5
) -> list[Take]:
    """k most semantically similar past AUTHORED takes — the few-shot set."""
    rows = (
        await session.execute(
            select(Take)
            .where(
                Take.user_id == user_id,
                Take.source == TakeSource.AUTHORED,
                Take.embedding.is_not(None),
            )
            .order_by(Take.embedding.cosine_distance(embedding))
            .limit(k)
        )
    ).scalars()
    return list(rows)


def style_constraints(profile: StyleProfile | None) -> dict[str, Any]:
    """The style profile as prompt constraints for Provocateur/Composer."""
    if profile is None or profile.take_count == 0:
        return {"cold_start": True}
    return {
        "sentence_length_mean": round(profile.sentence_length_mean, 1),
        "register": profile.register,
        "hedging_ratio": round(profile.hedging_ratio, 3),
        "profanity_ok": profile.profanity,
        "question_frequency": round(profile.question_frequency, 3),
        "signature_constructions": profile.signature_constructions[:8],
        "avoided_words": profile.avoided_words[:20],
        "sample_sentences": profile.sample_sentences[:5],
    }


async def voice_match_series(session: AsyncSession, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Median edit-distance ratio between suggestion and final text, by week.
    Falling = the learning works. Shown on the dashboard as voice match %."""
    takes = (
        (
            await session.execute(
                select(Take)
                .where(Take.user_id == user_id, Take.suggested_text != "")
                .order_by(Take.created_at)
            )
        )
        .scalars()
        .all()
    )
    by_week: dict[str, list[float]] = {}
    for t in takes:
        week = t.created_at.strftime("%G-W%V")
        by_week.setdefault(week, []).append(t.edit_distance_ratio)
    return [
        {"week": week,
         "voice_match_pct": round(100 * (1 - statistics.median(vals)), 1),
         "takes": len(vals)}
        for week, vals in sorted(by_week.items())
    ]


async def reset_voice(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(StyleProfile).where(StyleProfile.user_id == user_id))
    session.add(LearningEvent(user_id=user_id, loop="voice", trigger_kind="reset", detail={}))
