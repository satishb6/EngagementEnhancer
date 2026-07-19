"""ProviderRouter — the swap point.

Resolution order for every capability:
  1. user in local mode AND a healthy local provider offers it  -> local
  2. user has a BYOK credential for a cloud provider offering it -> that key,
     checked against their server-side daily cap
  3. platform cloud provider, billed to platform credits
  4. CapabilityUnavailable naming what's missing and how to fix it

Swapping a user from cloud to local changes zero lines outside providers/.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import ByokCredential, User, UserMode
from wire_api.providers import byok
from wire_api.providers.base import (
    Capability,
    CapabilityUnavailable,
    ProviderBinding,
)
from wire_api.providers.breaker import breaker_for
from wire_api.providers.cloud.anthropic import AnthropicTextProvider
from wire_api.providers.cloud.deepgram import DeepgramAudioProvider
from wire_api.providers.cloud.fal import FalImageProvider, FalVideoProvider
from wire_api.providers.cloud.google import GoogleTextProvider
from wire_api.providers.cloud.openai import OpenAIEmbeddingProvider, OpenAITextProvider
from wire_api.providers.local.comfyui import ComfyUIImageProvider, ComfyUIVideoProvider
from wire_api.providers.local.ollama import OllamaEmbeddingProvider, OllamaTextProvider
from wire_api.providers.local.whisper import FasterWhisperAudioProvider
from wire_api.settings import get_settings

_GUARDED_METHODS = {"complete", "embed", "generate", "transcribe", "poll"}


class GuardedProvider:
    """Proxy that runs every provider call through its circuit breaker."""

    def __init__(self, inner: Any, provider_id: str) -> None:
        self._inner = inner
        self._provider_id = provider_id
        self.provider_id = provider_id

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name not in _GUARDED_METHODS or not callable(attr):
            return attr
        breaker = breaker_for(self._provider_id)

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            breaker.check()
            try:
                result = await attr(*args, **kwargs)
            except Exception:
                breaker.record_failure()
                raise
            breaker.record_success()
            return result

        return wrapped


# which cloud vendors can serve which capability, in preference order,
# and how to build an adapter from an API key
_BYOK_FACTORIES: dict[Capability, list[tuple[str, Any]]] = {
    Capability.TEXT: [
        ("anthropic", AnthropicTextProvider),
        ("openai", OpenAITextProvider),
        ("google", GoogleTextProvider),
    ],
    Capability.EMBEDDING: [("openai", OpenAIEmbeddingProvider)],
    Capability.IMAGE: [("fal", FalImageProvider)],
    Capability.VIDEO: [("fal", FalVideoProvider)],
    Capability.AUDIO: [("deepgram", DeepgramAudioProvider)],
}


class ProviderRouter:
    def __init__(self) -> None:
        self._settings = get_settings()

    # ---- local ---------------------------------------------------------------
    def _local_candidate(self, capability: Capability) -> Any | None:
        s = self._settings
        match capability:
            case Capability.TEXT:
                return OllamaTextProvider(s.ollama_base_url)
            case Capability.EMBEDDING:
                return OllamaEmbeddingProvider(s.ollama_base_url)
            case Capability.IMAGE:
                return ComfyUIImageProvider(s.comfyui_base_url)
            case Capability.VIDEO:
                return ComfyUIVideoProvider(s.comfyui_base_url)
            case Capability.AUDIO:
                return FasterWhisperAudioProvider()
        return None

    # ---- platform ------------------------------------------------------------
    def _platform_candidate(self, capability: Capability) -> tuple[Any, str] | None:
        s = self._settings
        match capability:
            case Capability.TEXT if s.anthropic_api_key:
                return AnthropicTextProvider(s.anthropic_api_key), "ANTHROPIC_API_KEY"
            case Capability.TEXT if s.openai_api_key:
                return OpenAITextProvider(s.openai_api_key), "OPENAI_API_KEY"
            case Capability.EMBEDDING if s.openai_api_key:
                return OpenAIEmbeddingProvider(s.openai_api_key), "OPENAI_API_KEY"
            case Capability.IMAGE if s.fal_key:
                return FalImageProvider(s.fal_key), "FAL_KEY"
            case Capability.VIDEO if s.fal_key:
                return FalVideoProvider(s.fal_key), "FAL_KEY"
            case Capability.AUDIO if s.deepgram_api_key:
                return DeepgramAudioProvider(s.deepgram_api_key), "DEEPGRAM_API_KEY"
        return None

    _MISSING_HINT = {
        Capability.TEXT: "Set ANTHROPIC_API_KEY (platform), add a BYOK key, or start Ollama.",
        Capability.EMBEDDING: "Set OPENAI_API_KEY, add a BYOK OpenAI key, or start Ollama.",
        Capability.IMAGE: "Set FAL_KEY, add a BYOK fal key, or start ComfyUI.",
        Capability.VIDEO: "Set FAL_KEY, add a BYOK fal key, or start ComfyUI with a video workflow.",
        Capability.AUDIO: "Set DEEPGRAM_API_KEY or install the local extra (faster-whisper).",
    }

    async def resolve(
        self, capability: Capability, user: User | None, session: AsyncSession
    ) -> ProviderBinding:
        # 1 — local mode
        if user is not None and user.mode == UserMode.LOCAL:
            candidate = self._local_candidate(capability)
            if candidate is not None:
                breaker = breaker_for(candidate.provider_id)
                if not breaker.is_open and await candidate.healthy():
                    return ProviderBinding(
                        provider=GuardedProvider(candidate, candidate.provider_id),
                        capability=capability,
                        provider_id=candidate.provider_id,
                        billing_mode="local",
                    )
            # local users explicitly opted out of billing — do NOT silently
            # fall through to cloud. The caller surfaces the choice.
            raise CapabilityUnavailable(
                capability,
                "Local mode is on but no healthy local provider offers this. "
                + self._MISSING_HINT[capability],
            )

        # 2 — BYOK
        if user is not None:
            creds = (
                (
                    await session.execute(
                        select(ByokCredential).where(
                            ByokCredential.user_id == user.id,
                            ByokCredential.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_vendor = {c.provider: c for c in creds}
            for vendor, factory in _BYOK_FACTORIES.get(capability, []):
                cred = by_vendor.get(vendor)
                if cred is None:
                    continue
                if cred.spent_today_cents >= cred.daily_cap_cents:
                    continue  # cap hit — fall through to platform (billed in credits)
                if breaker_for(f"byok:{vendor}").is_open:
                    continue
                key = byok.decrypt_key(cred.encrypted_key)
                inner = factory(key)
                return ProviderBinding(
                    provider=GuardedProvider(inner, f"byok:{vendor}"),
                    capability=capability,
                    provider_id=f"byok:{vendor}",
                    billing_mode="byok",
                    byok_credential_id=str(cred.id),
                )

        # 3 — platform
        platform = self._platform_candidate(capability)
        if platform is not None:
            inner, _env = platform
            if not breaker_for(inner.provider_id).is_open:
                return ProviderBinding(
                    provider=GuardedProvider(inner, inner.provider_id),
                    capability=capability,
                    provider_id=inner.provider_id,
                    billing_mode="platform",
                )

        # 4 — nothing
        raise CapabilityUnavailable(capability, self._MISSING_HINT[capability])


_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router
