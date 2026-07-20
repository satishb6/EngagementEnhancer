"""Contract tests: every adapter structurally satisfies its protocol, and
the recorded-fixture round trips run offline via respx."""

import httpx
import pytest
import respx

from wire_api.providers.base import (
    AudioProvider,
    EmbeddingProvider,
    ImageProvider,
    Message,
    TextProvider,
    VideoProvider,
)
from wire_api.providers.cloud.anthropic import AnthropicTextProvider
from wire_api.providers.cloud.deepgram import DeepgramAudioProvider
from wire_api.providers.cloud.fal import FalImageProvider, FalVideoProvider
from wire_api.providers.cloud.google import GoogleTextProvider
from wire_api.providers.cloud.openai import OpenAIEmbeddingProvider, OpenAITextProvider
from wire_api.providers.local.comfyui import ComfyUIImageProvider, ComfyUIVideoProvider
from wire_api.providers.local.llamacpp import LlamaCppTextProvider
from wire_api.providers.local.ollama import OllamaEmbeddingProvider, OllamaTextProvider
from wire_api.providers.local.whisper import FasterWhisperAudioProvider


def test_text_adapters_satisfy_protocol() -> None:
    for adapter in (
        AnthropicTextProvider("k"), OpenAITextProvider("k"), GoogleTextProvider("k"),
        OllamaTextProvider("http://localhost:11434"), LlamaCppTextProvider(),
    ):
        assert isinstance(adapter, TextProvider), type(adapter)


def test_embedding_adapters_satisfy_protocol() -> None:
    for adapter in (
        OpenAIEmbeddingProvider("k"), OllamaEmbeddingProvider("http://localhost:11434"),
    ):
        assert isinstance(adapter, EmbeddingProvider), type(adapter)


def test_image_adapters_satisfy_protocol() -> None:
    for adapter in (FalImageProvider("k"), ComfyUIImageProvider("http://localhost:8188")):
        assert isinstance(adapter, ImageProvider), type(adapter)


def test_video_adapters_satisfy_protocol() -> None:
    for adapter in (FalVideoProvider("k"), ComfyUIVideoProvider("http://localhost:8188")):
        assert isinstance(adapter, VideoProvider), type(adapter)


def test_audio_adapters_satisfy_protocol() -> None:
    for adapter in (DeepgramAudioProvider("k"), FasterWhisperAudioProvider()):
        assert isinstance(adapter, AudioProvider), type(adapter)


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_fixture_roundtrip() -> None:
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": '{"headline": "Fed holds rates"}'}],
            "usage": {"input_tokens": 1840, "output_tokens": 96},
        })
    )
    result = await AnthropicTextProvider("test-key").complete(
        [Message("system", "s"), Message("user", "u")], max_tokens=100
    )
    assert "Fed holds" in result.text
    assert result.input_tokens == 1840
    assert result.meta.cost_cents > 0
    assert result.meta.provider_id == "anthropic"
    assert result.meta.model_id


@pytest.mark.asyncio
@respx.mock
async def test_openai_embed_fixture_roundtrip() -> None:
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json={
            "data": [{"embedding": [0.1] * 1536}, {"embedding": [0.2] * 1536}],
            "usage": {"prompt_tokens": 42},
        })
    )
    result = await OpenAIEmbeddingProvider("test-key").embed(["a", "b"])
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == 1536
    assert result.meta.provider_id == "openai-embed"


@pytest.mark.asyncio
@respx.mock
async def test_ollama_embed_pads_to_1536() -> None:
    respx.post("http://localhost:11434/api/embed").mock(
        return_value=httpx.Response(200, json={
            "embeddings": [[0.6, 0.8]], "prompt_eval_count": 5,
        })
    )
    result = await OllamaEmbeddingProvider("http://localhost:11434").embed(["x"])
    vec = result.vectors[0]
    assert len(vec) == 1536
    assert vec[0] == pytest.approx(0.6)  # normalised (0.6, 0.8 already unit)
    assert vec[1] == pytest.approx(0.8)
    assert all(v == 0.0 for v in vec[2:])
    assert result.meta.cost_cents == 0.0


@pytest.mark.asyncio
@respx.mock
async def test_fal_video_returns_job_not_bytes() -> None:
    """Video is async everywhere — the adapter returns a pollable job."""
    respx.post(
        "https://queue.fal.run/fal-ai/kling-video/v1.6/standard/image-to-video"
    ).mock(return_value=httpx.Response(200, json={"request_id": "req_123"}))
    job = await FalVideoProvider("test-key").generate("a scene", duration_s=20)
    assert job.job_ref == "req_123"
    assert job.status == "queued"
    assert job.meta.cost_cents == pytest.approx(200.0)  # 20s × 10¢/s
