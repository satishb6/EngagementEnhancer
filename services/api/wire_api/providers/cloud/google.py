"""Google Gemini text adapter."""

import time

import httpx

from wire_api.providers.base import Message, ResultMeta, TextResult
from wire_api.providers.costs import TEXT_RATES

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.0-flash"


class GoogleTextProvider:
    provider_id = "google"

    def __init__(self, api_key: str, default_model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._default_model = default_model

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        model = model or self._default_model
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        body: dict[str, object] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{BASE}/models/{model}:generateContent",
                params={"key": self._api_key},
                json=body,
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        usage = data.get("usageMetadata", {})
        in_tok = int(usage.get("promptTokenCount", 0))
        out_tok = int(usage.get("candidatesTokenCount", 0))
        rate = TEXT_RATES.get(model, TEXT_RATES["gemini-2.0-flash"])
        cost = (in_tok * rate.input_cents_per_mtok + out_tok * rate.output_cents_per_mtok) / 1e6
        text = "".join(
            part.get("text", "")
            for part in data["candidates"][0]["content"]["parts"]
        )
        return TextResult(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            meta=ResultMeta(cost, latency, self.provider_id, model),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
