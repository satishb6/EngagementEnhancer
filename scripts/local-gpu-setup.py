"""First-run setup for local GPU mode.

Probes the hardware, reports honestly what this machine can run and the
total disk the model pulls will need, asks before downloading anything.

Run from services/api:  uv run python ../../scripts/local-gpu-setup.py
"""

import asyncio
import sys

import httpx

sys.path.insert(0, "services/api")
sys.path.insert(0, ".")

from wire_api.settings import get_settings  # noqa: E402
from wire_api.system.hardware import capability_tier, probe  # noqa: E402

# model -> approximate download size in GB
PULLS_BY_TIER: dict[str, list[tuple[str, float]]] = {
    "text": [("llama3.1:8b", 4.9), ("nomic-embed-text", 0.3)],
    "text+image": [("llama3.1:8b", 4.9), ("nomic-embed-text", 0.3)],
    "text+image+short-video": [("llama3.1:8b", 4.9), ("nomic-embed-text", 0.3)],
    "full": [("llama3.1:8b", 4.9), ("qwen2.5:32b", 19.0), ("nomic-embed-text", 0.3)],
}

COMFY_NOTES = {
    "text+image": "ComfyUI: download SDXL-base (6.9GB) or Flux-schnell (23GB) into models/checkpoints.",
    "text+image+short-video": "ComfyUI: Flux-dev (23GB) + Wan2.2-i2v (28GB) for short video.",
    "full": "ComfyUI: Flux-dev (23GB) + Wan2.2-i2v (28GB); long-form renders are background jobs.",
}


async def main() -> None:
    caps = await probe()
    print("── WIRE local mode probe ──────────────────────────")
    print(f" GPU:       {caps.gpu.name or 'none detected'}")
    print(f" VRAM:      {caps.gpu.vram_total_mb / 1024:.1f} GB total, "
          f"{caps.gpu.vram_free_mb / 1024:.1f} GB free ({caps.gpu.backend})")
    tier, detail = capability_tier(caps.gpu.vram_total_mb)
    print(f" Tier:      {tier}")
    print(f" Reality:   {detail.get('note', '')}")
    print(f" Ollama:    {'reachable' if caps.ollama_reachable else 'NOT running'}")
    print(f" ComfyUI:   {'reachable' if caps.comfyui_reachable else 'NOT running'}")
    print()

    pulls = PULLS_BY_TIER.get(tier, [])
    if not pulls:
        print("No local models are worth pulling on this hardware. Cloud or BYOK "
              "mode will serve you better.")
        return
    total_gb = sum(size for _, size in pulls)
    print(f"Planned Ollama pulls ({total_gb:.1f} GB total):")
    for name, size in pulls:
        state = "already pulled" if any(name in m for m in caps.ollama_models) else f"{size:.1f} GB"
        print(f"  - {name}  [{state}]")
    if tier in COMFY_NOTES:
        print(f"\nManual step — {COMFY_NOTES[tier]}")

    if not caps.ollama_reachable:
        print("\nStart Ollama first (`ollama serve` or "
              "`docker compose --profile local-gpu up`), then re-run.")
        return

    answer = input(f"\nDownload {total_gb:.1f} GB now? [y/N] ").strip().lower()
    if answer != "y":
        print("Skipped. Re-run any time.")
        return

    settings = get_settings()
    async with httpx.AsyncClient(timeout=None) as client:
        for name, _ in pulls:
            if any(name in m for m in caps.ollama_models):
                continue
            print(f"pulling {name} …")
            async with client.stream(
                "POST", f"{settings.ollama_base_url}/api/pull", json={"model": name}
            ) as resp:
                async for line in resp.aiter_lines():
                    if '"status"' in line:
                        print("  " + line[:100], end="\r")
            print(f"\n  {name} done")
    print("\nLocal mode ready. Set LOCAL_MODE=1 (or switch in Studio → Mode).")


if __name__ == "__main__":
    asyncio.run(main())
