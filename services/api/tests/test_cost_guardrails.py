"""The suite that protects the unit economics.

The most important test here greps the codebase: no background task may be
able to CREATE a video job. The only writers of video jobs must live in
wire_api/generation/video.py, and its creation entrypoint must be reachable
only from the generation router.
"""

import re
from pathlib import Path

from wire_api.models import ContentType, Entitlement, GenerationJob, GenerationTier, Tier
from wire_api.generation.tiers import TIER_BY_CONTENT_TYPE, TierViolation, assert_tier_allowed

API_ROOT = Path(__file__).resolve().parents[1] / "wire_api"


def _python_files() -> list[Path]:
    return [p for p in API_ROOT.rglob("*.py") if ".venv" not in p.parts]


def test_no_video_job_creation_outside_video_module() -> None:
    """Video jobs (VIDEO_SHORT/VIDEO_LONG) may be constructed only in
    generation/video.py — which is called only by the generation router."""
    offenders: list[str] = []
    creation = re.compile(r"GenerationJob\(")
    for path in _python_files():
        rel = path.relative_to(API_ROOT).as_posix()
        if rel in ("generation/video.py",):
            continue
        text = path.read_text(encoding="utf-8")
        for match in creation.finditer(text):
            window = text[match.start():match.start() + 800]
            if "VIDEO" in window.upper() and "content_type" in window:
                offenders.append(rel)
    assert not offenders, f"video job constructed outside video.py: {offenders}"


def test_worker_has_no_video_creation_task() -> None:
    """The Celery module may poll video jobs; it may never create one."""
    worker = (API_ROOT / "worker.py").read_text(encoding="utf-8")
    assert "request_video" not in worker
    assert "approve_storyboard" not in worker
    # the poller is allowed — and must be present
    assert "poll_running_video_jobs" in worker


def test_request_video_called_only_from_router() -> None:
    callers = []
    for path in _python_files():
        rel = path.relative_to(API_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?<!def )request_video\(", text) and rel != "generation/video.py":
            callers.append(rel)
    assert callers == ["generation/router.py"], (
        f"request_video callable from {callers}; only the router may call it"
    )


def test_tier_gate_rejects_non_user_initiated_video() -> None:
    ent = Entitlement(tier=Tier.PRO, can_video=True, variant_count=3)
    job = GenerationJob(
        content_type=ContentType.VIDEO_SHORT,
        tier=GenerationTier.ON_DEMAND,
        user_initiated=False,
        variant_index=0,
    )
    try:
        assert_tier_allowed(job, ent)
        raise AssertionError("gate allowed a non-user-initiated video job")
    except TierViolation:
        pass


def test_tier_gate_rejects_video_without_entitlement() -> None:
    ent = Entitlement(tier=Tier.FREE, can_video=False, variant_count=1)
    job = GenerationJob(
        content_type=ContentType.VIDEO_SHORT,
        tier=GenerationTier.ON_DEMAND,
        user_initiated=True,
        variant_index=0,
    )
    try:
        assert_tier_allowed(job, ent)
        raise AssertionError("gate allowed video on the free tier")
    except TierViolation:
        pass


def test_tier_gate_rejects_free_tier_extra_variants() -> None:
    ent = Entitlement(tier=Tier.FREE, can_video=False, variant_count=1)
    job = GenerationJob(
        content_type=ContentType.TEXT,
        tier=GenerationTier.EAGER,
        user_initiated=True,
        variant_index=1,  # second variant — over the free cap
    )
    try:
        assert_tier_allowed(job, ent)
        raise AssertionError("gate allowed a second variant on free tier")
    except TierViolation:
        pass


def test_tier_mapping_is_complete() -> None:
    assert set(TIER_BY_CONTENT_TYPE) == set(ContentType)
    assert TIER_BY_CONTENT_TYPE[ContentType.VIDEO_SHORT] is GenerationTier.ON_DEMAND
    assert TIER_BY_CONTENT_TYPE[ContentType.VIDEO_LONG] is GenerationTier.GATED


def test_every_generation_path_estimates_before_execution() -> None:
    """Both job factories persist cost_estimate_cents before dispatch."""
    orchestrator = (API_ROOT / "generation" / "orchestrator.py").read_text(encoding="utf-8")
    video = (API_ROOT / "generation" / "video.py").read_text(encoding="utf-8")
    for source in (orchestrator, video):
        creation = source.index("GenerationJob(")
        estimate = source.index("cost_estimate_cents")
        assert abs(estimate - creation) < 1500, "estimate not set at job creation"
