"""Cost estimation — callable WITHOUT running the job.

Rates are worst-case list prices in cents. Estimates feed three places:
the pre-run persisted estimate on every generation_job, the BYOK preflight
shown to the user, and the credit charge table. Video estimation is
per-second and must stay accurate; drift >20% between estimate and actual
raises an alert in the orchestrator.
"""

from dataclasses import dataclass
from typing import Any

from wire_api.providers.base import Capability


@dataclass(frozen=True)
class TextRate:
    input_cents_per_mtok: float
    output_cents_per_mtok: float


# cents per million tokens
TEXT_RATES: dict[str, TextRate] = {
    "claude-haiku-4-5-20251001": TextRate(100, 500),
    "claude-sonnet-5": TextRate(300, 1500),
    "gpt-4o-mini": TextRate(15, 60),
    "gemini-2.0-flash": TextRate(10, 40),
    "local": TextRate(0, 0),
}

EMBED_CENTS_PER_MTOK = 2.0  # text-embedding-3-small
IMAGE_CENTS: dict[str, float] = {
    "fal-flux-schnell": 0.3,
    "fal-flux-dev": 2.5,
    "local-comfyui": 0.0,
}
VIDEO_CENTS_PER_SECOND: dict[str, float] = {
    "fal-kling-video": 10.0,   # ~$2.00 / 20s
    "fal-wan-video": 8.0,
    "local-comfyui": 0.0,
}
AUDIO_CENTS_PER_MINUTE = 0.43  # deepgram nova-2
PUBLISH_CENTS = 10.0


def estimate_cost(capability: Capability, params: dict[str, Any]) -> float:
    """Return the worst-case cost in cents for a call with these params."""
    if capability is Capability.TEXT:
        model = str(params.get("model", "claude-haiku-4-5-20251001"))
        rate = TEXT_RATES.get(model, TEXT_RATES["claude-sonnet-5"])
        in_tok = int(params.get("input_tokens", 2000))
        out_tok = int(params.get("max_tokens", 1024))
        return (in_tok * rate.input_cents_per_mtok + out_tok * rate.output_cents_per_mtok) / 1e6

    if capability is Capability.EMBEDDING:
        tokens = int(params.get("tokens", 500)) * int(params.get("n", 1))
        return tokens * EMBED_CENTS_PER_MTOK / 1e6

    if capability is Capability.IMAGE:
        model = str(params.get("model", "fal-flux-dev"))
        return IMAGE_CENTS.get(model, 2.5) * int(params.get("n", 1))

    if capability is Capability.VIDEO:
        model = str(params.get("model", "fal-kling-video"))
        seconds = float(params.get("duration_s", 5))
        return VIDEO_CENTS_PER_SECOND.get(model, 10.0) * seconds

    if capability is Capability.AUDIO:
        minutes = float(params.get("duration_s", 60)) / 60.0
        return AUDIO_CENTS_PER_MINUTE * minutes

    raise ValueError(f"unknown capability {capability}")
