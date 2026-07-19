"""sentence-transformers adapter — local embeddings, padded to EMBED_DIM."""

import asyncio
import time
from typing import Any

from wire_api.providers.base import EmbeddingResult, ResultMeta
from wire_api.providers.local.ollama import _pad

MODEL_NAME = "all-MiniLM-L6-v2"

_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


class SentenceTransformersEmbeddingProvider:
    provider_id = "sentence-transformers"

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        t0 = time.perf_counter()

        def _run() -> list[list[float]]:
            model = _get_model()
            return [list(map(float, v)) for v in model.encode(texts, normalize_embeddings=True)]

        raw = await asyncio.to_thread(_run)
        latency = (time.perf_counter() - t0) * 1000
        return EmbeddingResult(
            vectors=[_pad(v) for v in raw],
            input_tokens=0,
            meta=ResultMeta(0.0, latency, self.provider_id, MODEL_NAME),
        )

    async def healthy(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401

            return True
        except ImportError:
            return False
