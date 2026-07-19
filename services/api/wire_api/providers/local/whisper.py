"""faster-whisper adapter — local transcription for voice takes.

Imported lazily: the model load costs seconds and hundreds of MB, so it only
happens on first use, and only when the `local` extra is installed.
"""

import asyncio
import io
import time
from typing import Any

from wire_api.providers.base import ResultMeta, TranscriptResult

MODEL_SIZE = "small"

_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL_SIZE, device="auto", compute_type="auto")
    return _model


class FasterWhisperAudioProvider:
    provider_id = "faster-whisper"

    async def transcribe(
        self, audio: bytes, *, content_type: str = "audio/wav"
    ) -> TranscriptResult:
        t0 = time.perf_counter()

        def _run() -> tuple[str, float]:
            model = _get_model()
            segments, info = model.transcribe(io.BytesIO(audio))
            text = " ".join(seg.text.strip() for seg in segments)
            return text, float(info.duration)

        text, duration = await asyncio.to_thread(_run)
        latency = (time.perf_counter() - t0) * 1000
        return TranscriptResult(
            text=text,
            duration_s=duration,
            meta=ResultMeta(0.0, latency, self.provider_id, MODEL_SIZE),
        )

    async def healthy(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except ImportError:
            return False
