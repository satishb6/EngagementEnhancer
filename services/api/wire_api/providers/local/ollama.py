"""Ollama adapters — local text + embeddings. Zero marginal cost."""

import time

import httpx

from wire_api.models.base import EMBED_DIM
from wire_api.providers.base import (
    EmbeddingResult,
    Message,
    ResultMeta,
    TextResult,
)

DEFAULT_TEXT_MODEL = "llama3.1:8b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


def _pad(vec: list[float]) -> list[float]:
    """L2-normalise then zero-pad to EMBED_DIM so local and cloud vectors
    live in the same column. Cosine ordering within a provider is preserved."""
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    normalised = [v / norm for v in vec]
    if len(normalised) >= EMBED_DIM:
        return normalised[:EMBED_DIM]
    return normalised + [0.0] * (EMBED_DIM - len(normalised))


class OllamaTextProvider:
    provider_id = "ollama"

    def __init__(self, base_url: str, default_model: str = DEFAULT_TEXT_MODEL) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        model = model or self._default_model
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        return TextResult(
            text=data["message"]["content"],
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            meta=ResultMeta(0.0, latency, self.provider_id, model),
        )

    async def pull_model(self, model: str) -> None:
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(f"{self._base_url}/api/pull",
                                     json={"model": model, "stream": False})
            resp.raise_for_status()

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


class OllamaEmbeddingProvider:
    provider_id = "ollama-embed"

    def __init__(self, base_url: str, model: str = DEFAULT_EMBED_MODEL) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        vectors = [_pad(v) for v in data["embeddings"]]
        return EmbeddingResult(
            vectors=vectors,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            meta=ResultMeta(0.0, latency, self.provider_id, self._model),
        )

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
