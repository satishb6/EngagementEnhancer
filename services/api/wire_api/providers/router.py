"""ProviderRouter — the swap point.

Resolution order for every capability:
  1. keys/provider sent by the frontend for THIS request (Studio engine panel)
  2. user in local mode AND a healthy local provider offers it  -> local
  3. user's stored BYOK credential                              -> that key
  4. platform env keys                                          -> platform
  5. the zero-key demo core (text/embedding/image)              -> demo
Video and audio have no demo tier — they raise CapabilityUnavailable with
the fix named. Swapping tiers changes zero lines outside providers/.
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
from wire_api.providers.cloud.gemini_embed import GeminiEmbeddingProvider
from wire_api.providers.cloud.google import GoogleTextProvider
from wire_api.providers.cloud.openai import OpenAIEmbeddingProvider, OpenAITextProvider
from wire_api.providers.cloud.openai_compat import VENDORS, OpenAICompatTextProvider
from wire_api.providers.demo import (
    DemoImageProvider,
    DemoTextProvider,
    HashEmbeddingProvider,
)
from wire_api.providers.local.comfyui import ComfyUIImageProvider, ComfyUIVideoProvider
from wire_api.providers.local.ollama import OllamaEmbeddingProvider, OllamaTextProvider
from wire_api.providers.local.whisper import FasterWhisperAudioProvider
from wire_api.providers.request_keys import get_request_engine
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


def _bind(inner: Any, mode: str, cred_id: str | None = None,
          capability: Capability = Capability.TEXT) -> ProviderBinding:
    return ProviderBinding(
        provider=GuardedProvider(inner, inner.provider_id),
        capability=capability,
        provider_id=inner.provider_id,
        billing_mode=mode,
        byok_credential_id=cred_id,
    )


def _text_from_key(vendor: str, key: str, model: str = "") -> Any | None:
    """Build a text adapter for any supported vendor name + key."""
    if vendor in VENDORS:
        return OpenAICompatTextProvider(vendor, key, model or None)
    if vendor == "anthropic":
        return AnthropicTextProvider(key, model) if model else AnthropicTextProvider(key)
    if vendor == "openai":
        return OpenAITextProvider(key, model) if model else OpenAITextProvider(key)
    if vendor in ("google", "gemini"):
        return GoogleTextProvider(key, model) if model else GoogleTextProvider(key)
    return None


# text-capable vendors in free-first preference order
_TEXT_PREFERENCE = ["groq", "google", "gemini", "openrouter", "anthropic",
                    "openai", "deepseek", "mistral", "xai"]


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

    # ---- request engine (frontend keys) --------------------------------------
    async def _from_request(self, capability: Capability) -> ProviderBinding | None:
        engine = get_request_engine()
        if engine.empty:
            return None

        if engine.provider == "demo":
            return self._demo(capability)
        if engine.provider == "ollama" and capability in (Capability.TEXT, Capability.EMBEDDING):
            candidate = self._local_candidate(capability)
            if candidate is not None and await candidate.healthy():
                return _bind(candidate, "local", capability=capability)

        if capability is Capability.TEXT:
            order = ([engine.provider] if engine.provider else []) + _TEXT_PREFERENCE
            for vendor in order:
                key = engine.keys.get(vendor) or engine.keys.get(
                    "google" if vendor == "gemini" else vendor
                )
                if not key:
                    continue
                inner = _text_from_key(vendor, key, engine.model)
                if inner is not None and not breaker_for(inner.provider_id).is_open:
                    return _bind(inner, "byok", capability=capability)

        if capability is Capability.EMBEDDING:
            gkey = engine.keys.get("google") or engine.keys.get("gemini")
            if gkey:
                return _bind(GeminiEmbeddingProvider(gkey), "byok", capability=capability)
            if engine.keys.get("openai"):
                return _bind(OpenAIEmbeddingProvider(engine.keys["openai"]), "byok",
                             capability=capability)

        if capability is Capability.IMAGE and engine.keys.get("fal"):
            return _bind(FalImageProvider(engine.keys["fal"]), "byok", capability=capability)
        if capability is Capability.VIDEO and engine.keys.get("fal"):
            return _bind(FalVideoProvider(engine.keys["fal"]), "byok", capability=capability)
        if capability is Capability.AUDIO and engine.keys.get("deepgram"):
            return _bind(DeepgramAudioProvider(engine.keys["deepgram"]), "byok",
                         capability=capability)
        return None

    # ---- platform ------------------------------------------------------------
    def _platform_candidate(self, capability: Capability) -> Any | None:
        s = self._settings
        match capability:
            case Capability.TEXT:
                if s.groq_api_key:
                    return OpenAICompatTextProvider("groq", s.groq_api_key)
                if s.google_api_key:
                    return GoogleTextProvider(s.google_api_key)
                if s.anthropic_api_key:
                    return AnthropicTextProvider(s.anthropic_api_key)
                if s.openrouter_api_key:
                    return OpenAICompatTextProvider("openrouter", s.openrouter_api_key)
                if s.openai_api_key:
                    return OpenAITextProvider(s.openai_api_key)
            case Capability.EMBEDDING:
                if s.google_api_key:
                    return GeminiEmbeddingProvider(s.google_api_key)
                if s.openai_api_key:
                    return OpenAIEmbeddingProvider(s.openai_api_key)
            case Capability.IMAGE if s.fal_key:
                return FalImageProvider(s.fal_key)
            case Capability.VIDEO if s.fal_key:
                return FalVideoProvider(s.fal_key)
            case Capability.AUDIO if s.deepgram_api_key:
                return DeepgramAudioProvider(s.deepgram_api_key)
        return None

    # ---- demo ----------------------------------------------------------------
    def _demo(self, capability: Capability) -> ProviderBinding | None:
        match capability:
            case Capability.TEXT:
                return _bind(DemoTextProvider(), "demo", capability=capability)
            case Capability.EMBEDDING:
                return _bind(HashEmbeddingProvider(), "demo", capability=capability)
            case Capability.IMAGE:
                return _bind(DemoImageProvider(), "demo", capability=capability)
        return None

    _MISSING_HINT = {
        Capability.TEXT: "Add a free Groq or Google Gemini key in Studio → Engine.",
        Capability.EMBEDDING: "Add a free Google Gemini key in Studio → Engine.",
        Capability.IMAGE: "Add a fal.ai key in Studio → Engine for real images.",
        Capability.VIDEO: "Video needs a fal.ai key (Studio → Engine) or local ComfyUI.",
        Capability.AUDIO: "Voice takes need a Deepgram key or the local whisper extra.",
    }

    async def resolve(
        self, capability: Capability, user: User | None, session: AsyncSession
    ) -> ProviderBinding:
        # 1 — frontend-supplied engine for this request
        from_request = await self._from_request(capability)
        if from_request is not None:
            return from_request

        # 2 — local mode
        if user is not None and user.mode == UserMode.LOCAL:
            candidate = self._local_candidate(capability)
            if candidate is not None:
                breaker = breaker_for(candidate.provider_id)
                if not breaker.is_open and await candidate.healthy():
                    return _bind(candidate, "local", capability=capability)
            demo = self._demo(capability)
            if demo is not None:
                return demo
            raise CapabilityUnavailable(
                capability,
                "Local mode is on but no healthy local provider offers this. "
                + self._MISSING_HINT[capability],
            )

        # 3 — stored BYOK
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
            for vendor in _TEXT_PREFERENCE if capability is Capability.TEXT else []:
                cred = by_vendor.get(vendor)
                if cred is None or cred.spent_today_cents >= cred.daily_cap_cents:
                    continue
                if breaker_for(f"byok:{vendor}").is_open:
                    continue
                inner = _text_from_key(vendor, byok.decrypt_key(cred.encrypted_key))
                if inner is not None:
                    return ProviderBinding(
                        provider=GuardedProvider(inner, f"byok:{vendor}"),
                        capability=capability, provider_id=f"byok:{vendor}",
                        billing_mode="byok", byok_credential_id=str(cred.id),
                    )
            cred_map = {
                Capability.EMBEDDING: ("google", lambda k: GeminiEmbeddingProvider(k)),
                Capability.IMAGE: ("fal", lambda k: FalImageProvider(k)),
                Capability.VIDEO: ("fal", lambda k: FalVideoProvider(k)),
                Capability.AUDIO: ("deepgram", lambda k: DeepgramAudioProvider(k)),
            }
            if capability in cred_map:
                vendor, factory = cred_map[capability]
                cred = by_vendor.get(vendor)
                if cred is not None and cred.spent_today_cents < cred.daily_cap_cents:
                    inner = factory(byok.decrypt_key(cred.encrypted_key))
                    return ProviderBinding(
                        provider=GuardedProvider(inner, f"byok:{vendor}"),
                        capability=capability, provider_id=f"byok:{vendor}",
                        billing_mode="byok", byok_credential_id=str(cred.id),
                    )

        # 4 — platform env keys
        platform = self._platform_candidate(capability)
        if platform is not None and not breaker_for(platform.provider_id).is_open:
            return _bind(platform, "platform", capability=capability)

        # 5 — the demo core: the app never breaks for want of a key
        demo = self._demo(capability)
        if demo is not None:
            return demo

        raise CapabilityUnavailable(capability, self._MISSING_HINT[capability])


_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router
