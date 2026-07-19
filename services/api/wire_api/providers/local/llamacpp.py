"""llama.cpp server adapter — OpenAI-compatible local text endpoint.

Points at a running llama-server (`llama-server -m model.gguf --port 8080`).
"""

import time

import httpx

from wire_api.providers.base import Message, ResultMeta, TextResult


class LlamaCppTextProvider:
    provider_id = "llamacpp"

    def __init__(self, base_url: str = "http://localhost:8080", model: str = "local-gguf") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json={
                    "model": model or self._model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        usage = data.get("usage", {})
        return TextResult(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            meta=ResultMeta(0.0, latency, self.provider_id, model or self._model),
        )

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
