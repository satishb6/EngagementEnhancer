"""Provider protocols — the abstraction every model call goes through.

Business logic calls `router.resolve(capability, user)` and never knows
whether the answer is fal.ai, the user's own key, or a ComfyUI instance on
their desk. No direct SDK calls exist outside wire_api/providers/.
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class Capability(enum.StrEnum):
    TEXT = "text"
    EMBEDDING = "embedding"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class CapabilityUnavailable(RuntimeError):
    """Raised when no provider can serve a capability. The message names
    what's missing and how to fix it — it surfaces directly in the UI."""

    def __init__(self, capability: Capability, detail: str) -> None:
        self.capability = capability
        self.detail = detail
        super().__init__(f"No provider available for '{capability}'. {detail}")


@dataclass(frozen=True)
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass
class ResultMeta:
    cost_cents: float
    latency_ms: float
    provider_id: str
    model_id: str


@dataclass
class TextResult:
    text: str
    input_tokens: int
    output_tokens: int
    meta: ResultMeta


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    input_tokens: int
    meta: ResultMeta


@dataclass
class ImageResult:
    # exactly one of url / path / b64 is set depending on adapter
    url: str = ""
    path: str = ""
    b64: str = ""
    width: int = 0
    height: int = 0
    seed: int | None = None
    meta: ResultMeta = field(default_factory=lambda: ResultMeta(0, 0, "", ""))


@dataclass
class VideoJob:
    """Video is async everywhere: the adapter returns a job handle that the
    orchestrator polls. Never awaited inside a request handler."""

    job_ref: str
    status: str  # queued | running | succeeded | failed
    url: str = ""
    duration_s: float = 0.0
    meta: ResultMeta = field(default_factory=lambda: ResultMeta(0, 0, "", ""))


@dataclass
class TranscriptResult:
    text: str
    duration_s: float
    meta: ResultMeta


@runtime_checkable
class TextProvider(Protocol):
    provider_id: str

    async def complete(
        self, messages: list[Message], *, model: str | None = None, max_tokens: int = 1024
    ) -> TextResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_id: str

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


@runtime_checkable
class ImageProvider(Protocol):
    provider_id: str

    async def generate(
        self, prompt: str, *, size: str = "1024x1024", n: int = 1, seed: int | None = None
    ) -> list[ImageResult]: ...


@runtime_checkable
class VideoProvider(Protocol):
    provider_id: str

    async def generate(
        self, prompt: str, *, init_image: str | None = None, duration_s: int = 5
    ) -> VideoJob: ...

    async def poll(self, job_ref: str) -> VideoJob: ...


@runtime_checkable
class AudioProvider(Protocol):
    provider_id: str

    async def transcribe(self, audio: bytes, *, content_type: str = "audio/wav") -> TranscriptResult: ...


@runtime_checkable
class HealthCheckable(Protocol):
    async def healthy(self) -> bool: ...


AnyProvider = (
    TextProvider | EmbeddingProvider | ImageProvider | VideoProvider | AudioProvider
)


@dataclass
class ProviderBinding:
    """What the router hands back: the provider plus billing context."""

    provider: Any
    capability: Capability
    provider_id: str
    # platform | byok | local — decides who pays and which meters move
    billing_mode: str
    byok_credential_id: str | None = None
