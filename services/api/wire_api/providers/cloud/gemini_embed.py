"""Google Gemini embeddings — a genuinely free embedding tier."""

import time

import httpx

from wire_api.providers.base import EmbeddingResult, ResultMeta
from wire_api.providers.local.ollama import _pad

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "text-embedding-004"  # 768-dim, padded to EMBED_DIM


class GeminiEmbeddingProvider:
    provider_id = "gemini-embed"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        t0 = time.perf_counter()
        body = {
            "requests": [
                {"model": f"models/{MODEL}", "content": {"parts": [{"text": t[:8000]}]}}
                for t in texts
            ]
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE}/models/{MODEL}:batchEmbedContents",
                params={"key": self._api_key},
                json=body,
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        vectors = [_pad(e["values"]) for e in data.get("embeddings", [])]
        return EmbeddingResult(
            vectors=vectors, input_tokens=0,
            meta=ResultMeta(0.0, latency, self.provider_id, MODEL),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
