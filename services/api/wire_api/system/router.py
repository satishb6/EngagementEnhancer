"""System endpoints: capability probe, mode switching, learning resets,
voice match, quota meters."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from wire_api.auth.deps import DB, CurrentUser
from wire_api.learning.format_loop import reset_format
from wire_api.learning.taste import reset_taste
from wire_api.learning.timing import reset_timing
from wire_api.learning.voice import reset_voice, voice_match_series
from wire_api.models import UserMode
from wire_api.settings import get_settings
from wire_api.system.hardware import probe
from wire_api.tracing.emit import get_redis

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    caps = await probe()
    return {
        "gpu": {
            "name": caps.gpu.name,
            "vram_total_mb": caps.gpu.vram_total_mb,
            "vram_free_mb": caps.gpu.vram_free_mb,
            "backend": caps.gpu.backend,
        },
        "ollama": {"reachable": caps.ollama_reachable, "models": caps.ollama_models},
        "comfyui": {"reachable": caps.comfyui_reachable},
        "whisper_installed": caps.whisper_installed,
        "tier": caps.tier,
        "tier_detail": caps.tier_detail,
    }


class ModeIn(BaseModel):
    mode: UserMode


@router.post("/mode")
async def set_mode(body: ModeIn, user: CurrentUser, session: DB) -> dict[str, str]:
    if body.mode is UserMode.LOCAL:
        caps = await probe()
        if not caps.ollama_reachable:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Local mode needs Ollama running. Start it (or `docker compose "
                "--profile local-gpu up`) and try again.",
            )
    user.mode = body.mode
    await session.commit()
    return {"mode": body.mode.value}


@router.get("/meters")
async def meters(user: CurrentUser, session: DB) -> dict[str, Any]:
    """The Wire Room's top strip: quota + budget numbers that break the
    product when nobody watches them."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from wire_api.billing.credits import balance
    from wire_api.models import GenerationJob
    from wire_api.models.base import utcnow

    settings = get_settings()
    redis = get_redis()
    date_key = utcnow().strftime("%Y-%m-%d")
    youtube_used = int(await redis.get(f"wire:youtube:quota:{date_key}") or 0)

    since = utcnow() - timedelta(hours=24)
    burned = (
        await session.execute(
            select(func.coalesce(func.sum(GenerationJob.credits_charged), 0)).where(
                GenerationJob.user_id == user.id,
                GenerationJob.created_at >= since,
            )
        )
    ).scalar_one()
    spend_cents = (
        await session.execute(
            select(func.coalesce(func.sum(GenerationJob.cost_actual_cents), 0)).where(
                GenerationJob.user_id == user.id,
                GenerationJob.created_at >= since,
            )
        )
    ).scalar_one()

    result: dict[str, Any] = {
        "youtube_units": {"used": youtube_used,
                          "cap": settings.youtube_daily_quota_units},
        "credits": {"burned_today": int(burned),
                    "balance": await balance(session, user.id)},
        "spend_today_cents": int(spend_cents),
    }
    if user.mode is UserMode.LOCAL:
        caps = await probe()
        result["local"] = {
            "vram_used_mb": caps.gpu.vram_total_mb - caps.gpu.vram_free_mb,
            "vram_total_mb": caps.gpu.vram_total_mb,
        }
    return result


@router.post("/learning/reset/{loop}")
async def reset_learning_loop(loop: str, user: CurrentUser, session: DB) -> dict[str, str]:
    """All four loops are resettable independently."""
    resets = {"taste": reset_taste, "voice": reset_voice,
              "format": reset_format, "timing": reset_timing}
    if loop not in resets:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Unknown loop '{loop}'. One of: {sorted(resets)}")
    await resets[loop](session, user.id)
    await session.commit()
    return {"reset": loop}


@router.get("/learning/voice-match")
async def voice_match(user: CurrentUser, session: DB) -> dict[str, Any]:
    """THE metric: median edit distance between suggested and final text,
    falling week over week — shown as a percentage."""
    series = await voice_match_series(session, user.id)
    return {"series": series,
            "current": series[-1]["voice_match_pct"] if series else None}
