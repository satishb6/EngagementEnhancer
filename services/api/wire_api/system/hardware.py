"""Hardware detection for local GPU mode. Honest about what won't run."""

import asyncio
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

import httpx

from wire_api.settings import get_settings


@dataclass
class GPUInfo:
    name: str = ""
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    backend: str = "none"  # cuda | rocm | metal | none


@dataclass
class LocalCapabilities:
    gpu: GPUInfo = field(default_factory=GPUInfo)
    ollama_reachable: bool = False
    ollama_models: list[str] = field(default_factory=list)
    comfyui_reachable: bool = False
    whisper_installed: bool = False
    tier: str = "none"
    tier_detail: dict[str, Any] = field(default_factory=dict)


def _detect_nvidia() -> GPUInfo:
    if shutil.which("nvidia-smi") is None:
        return GPUInfo()
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()
        if not out:
            return GPUInfo()
        name, total, free = (part.strip() for part in out[0].split(","))
        return GPUInfo(name=name, vram_total_mb=int(float(total)),
                       vram_free_mb=int(float(free)), backend="cuda")
    except (subprocess.SubprocessError, ValueError):
        return GPUInfo()


def _detect_gpu() -> GPUInfo:
    gpu = _detect_nvidia()
    if gpu.backend != "none":
        return gpu
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        # Apple silicon: unified memory; report system RAM as an upper bound
        try:
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                 text=True, timeout=5, check=True).stdout.strip()
            total_mb = int(out) // (1024 * 1024)
            return GPUInfo(name="Apple Silicon", vram_total_mb=total_mb,
                           vram_free_mb=total_mb // 2, backend="metal")
        except (subprocess.SubprocessError, ValueError):
            pass
    return GPUInfo()


def capability_tier(vram_mb: int) -> tuple[str, dict[str, Any]]:
    """Be honest about what won't run. Never promise video on 8GB."""
    gb = vram_mb / 1024
    if gb < 1:
        return "none", {"note": "No GPU detected. Local mode limited to CPU text via Ollama "
                                "(slow) and embeddings."}
    if gb < 8:
        return "text", {"text": "7B quantised", "embeddings": True, "image": False,
                        "video": False,
                        "note": "Text and embeddings only. Image and video need 8GB+."}
    if gb < 16:
        return "text+image", {"text": "7-13B", "embeddings": True,
                              "image": "SDXL / Flux-schnell", "video": False,
                              "note": "Video on this card is unrealistic; use cloud for video."}
    if gb < 24:
        return "text+image+short-video", {
            "text": "up to 32B quantised", "embeddings": True, "image": "Flux-dev",
            "video": "~5s clips (Wan/Hunyuan), several minutes per generation",
            "note": "Short clips only, and they take minutes — the queue shows real ETAs."}
    return "full", {
        "text": "large models", "embeddings": True, "image": "Flux-dev",
        "video": "short + long-form as a background job measured in tens of minutes",
        "note": "Everything runs. Long-form video is still a coffee-length wait."}


async def probe() -> LocalCapabilities:
    settings = get_settings()
    caps = LocalCapabilities(gpu=await asyncio.to_thread(_detect_gpu))

    async with httpx.AsyncClient(timeout=3) as client:
        try:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                caps.ollama_reachable = True
                caps.ollama_models = [
                    str(m.get("name", "")) for m in resp.json().get("models", [])
                ]
        except httpx.HTTPError:
            pass
        try:
            resp = await client.get(f"{settings.comfyui_base_url}/system_stats")
            caps.comfyui_reachable = resp.status_code == 200
        except httpx.HTTPError:
            pass

    try:
        import faster_whisper  # noqa: F401

        caps.whisper_installed = True
    except ImportError:
        caps.whisper_installed = False

    caps.tier, caps.tier_detail = capability_tier(caps.gpu.vram_total_mb)
    return caps
