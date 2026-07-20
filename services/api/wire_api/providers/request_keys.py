"""Per-request BYOK from the frontend.

The Studio engine panel stores keys in the user's browser (localStorage) and
sends them on each request as headers. They live for the request only —
never logged, never persisted server-side, redacted from traces by the
tracing guard. This is the EIP model: the server is a relay, the user owns
their keys.

Headers:
  X-Wire-Keys      JSON: {"groq": "gsk_...", "google": "AIza...", ...}
  X-Wire-Provider  preferred text provider id (e.g. "groq", "demo", "ollama")
  X-Wire-Model     optional explicit model override
"""

import json
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class RequestEngine:
    keys: dict[str, str] = field(default_factory=dict)
    provider: str = ""  # "" = auto
    model: str = ""

    @property
    def empty(self) -> bool:
        return not self.keys and not self.provider and not self.model


_engine: ContextVar[RequestEngine | None] = ContextVar("wire_request_engine", default=None)


def set_request_engine(
    keys_header: str | None, provider: str | None, model: str | None
) -> None:
    keys: dict[str, str] = {}
    if keys_header:
        try:
            parsed = json.loads(keys_header)
            if isinstance(parsed, dict):
                keys = {
                    str(k).lower(): str(v)
                    for k, v in parsed.items()
                    if isinstance(v, str) and v.strip()
                }
        except json.JSONDecodeError:
            keys = {}
    _engine.set(RequestEngine(keys=keys, provider=(provider or "").lower(),
                              model=model or ""))


def get_request_engine() -> RequestEngine:
    return _engine.get() or RequestEngine()


def clear_request_engine() -> None:
    _engine.set(None)
