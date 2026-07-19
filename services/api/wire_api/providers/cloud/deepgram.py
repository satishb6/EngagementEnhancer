"""Deepgram audio transcription adapter."""

import time

import httpx

from wire_api.providers.base import ResultMeta, TranscriptResult
from wire_api.providers.costs import AUDIO_CENTS_PER_MINUTE

API_URL = "https://api.deepgram.com/v1/listen"
MODEL = "nova-2"


class DeepgramAudioProvider:
    provider_id = "deepgram"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def transcribe(
        self, audio: bytes, *, content_type: str = "audio/wav"
    ) -> TranscriptResult:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                API_URL,
                params={"model": MODEL, "smart_format": "true"},
                content=audio,
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Content-Type": content_type,
                },
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        duration = float(data.get("metadata", {}).get("duration", 0.0))
        alt = data["results"]["channels"][0]["alternatives"][0]
        return TranscriptResult(
            text=alt.get("transcript", ""),
            duration_s=duration,
            meta=ResultMeta(
                cost_cents=AUDIO_CENTS_PER_MINUTE * duration / 60.0,
                latency_ms=latency,
                provider_id=self.provider_id,
                model_id=MODEL,
            ),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
