"""Anthropic text adapter. Raw HTTP — the abstraction owns retries and cost."""

import time

import httpx

from wire_api.providers.base import Message, ResultMeta, TextResult
from wire_api.providers.costs import TEXT_RATES

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicTextProvider:
    provider_id = "anthropic"

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._default_model = default_model

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        model = model or self._default_model
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        chat = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        body: dict[str, object] = {"model": model, "max_tokens": max_tokens, "messages": chat}
        if system:
            body["system"] = system

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                API_URL,
                json=body,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000

        in_tok = int(data["usage"]["input_tokens"])
        out_tok = int(data["usage"]["output_tokens"])
        rate = TEXT_RATES.get(model, TEXT_RATES["claude-sonnet-5"])
        cost = (in_tok * rate.input_cents_per_mtok + out_tok * rate.output_cents_per_mtok) / 1e6
        text = "".join(
            block["text"] for block in data["content"] if block.get("type") == "text"
        )
        return TextResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            meta=ResultMeta(cost_cents=cost, latency_ms=latency,
                            provider_id=self.provider_id, model_id=model),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
