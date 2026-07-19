"""OpenAI adapters: text (fallback) and embeddings (the platform default)."""

import time

import httpx

from wire_api.providers.base import (
    EmbeddingResult,
    Message,
    ResultMeta,
    TextResult,
)
from wire_api.providers.costs import EMBED_CENTS_PER_MTOK, TEXT_RATES

CHAT_URL = "https://api.openai.com/v1/chat/completions"
EMBED_URL = "https://api.openai.com/v1/embeddings"
EMBED_MODEL = "text-embedding-3-small"


class OpenAITextProvider:
    provider_id = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self._default_model = default_model

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        model = model or self._default_model
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                CHAT_URL,
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        in_tok = int(data["usage"]["prompt_tokens"])
        out_tok = int(data["usage"]["completion_tokens"])
        rate = TEXT_RATES.get(model, TEXT_RATES["gpt-4o-mini"])
        cost = (in_tok * rate.input_cents_per_mtok + out_tok * rate.output_cents_per_mtok) / 1e6
        return TextResult(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=in_tok,
            output_tokens=out_tok,
            meta=ResultMeta(cost, latency, self.provider_id, model),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)


class OpenAIEmbeddingProvider:
    provider_id = "openai-embed"

    def __init__(self, api_key: str, model: str = EMBED_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                EMBED_URL,
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        tokens = int(data["usage"]["prompt_tokens"])
        vectors = [item["embedding"] for item in data["data"]]
        return EmbeddingResult(
            vectors=vectors,
            input_tokens=tokens,
            meta=ResultMeta(tokens * EMBED_CENTS_PER_MTOK / 1e6, latency,
                            self.provider_id, self._model),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
