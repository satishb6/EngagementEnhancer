"""One adapter, five vendors. Groq, DeepSeek, Mistral, OpenRouter, and xAI
all speak the OpenAI chat-completions dialect — only base URL, key, and
default model differ. Groq, OpenRouter's :free models, and Gemini's free
tier are the no-money testing path."""

import time
from dataclasses import dataclass

import httpx

from wire_api.providers.base import Message, ResultMeta, TextResult
from wire_api.providers.costs import TEXT_RATES, TextRate


@dataclass(frozen=True)
class CompatVendor:
    provider_id: str
    base_url: str
    default_model: str
    free_tier: bool


VENDORS: dict[str, CompatVendor] = {
    "groq": CompatVendor(
        "groq", "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile", free_tier=True,
    ),
    "openrouter": CompatVendor(
        "openrouter", "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.3-70b-instruct:free", free_tier=True,
    ),
    "deepseek": CompatVendor(
        "deepseek", "https://api.deepseek.com/v1", "deepseek-chat", free_tier=False,
    ),
    "mistral": CompatVendor(
        "mistral", "https://api.mistral.ai/v1", "mistral-small-latest", free_tier=False,
    ),
    "xai": CompatVendor(
        "xai", "https://api.x.ai/v1", "grok-3-mini", free_tier=False,
    ),
}


class OpenAICompatTextProvider:
    def __init__(self, vendor: str, api_key: str, model: str | None = None) -> None:
        spec = VENDORS[vendor]
        self.provider_id = spec.provider_id
        self._base_url = spec.base_url
        self._api_key = api_key
        self._default_model = model or spec.default_model
        self._free = spec.free_tier

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        model = model or self._default_model
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
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
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        rate = (
            TextRate(0, 0) if (self._free or ":free" in model)
            else TEXT_RATES.get(model, TextRate(20, 80))
        )
        cost = (in_tok * rate.input_cents_per_mtok + out_tok * rate.output_cents_per_mtok) / 1e6
        return TextResult(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=in_tok,
            output_tokens=out_tok,
            meta=ResultMeta(cost, latency, self.provider_id, model),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
