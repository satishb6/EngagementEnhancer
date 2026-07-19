"""ComfyUI adapter — local image and video via the HTTP API.

Workflows are parameterised JSON templates shipped in ./workflows/, not
hardcoded graphs. A single consumer GPU is serial: the orchestrator runs
local jobs with concurrency 1 and shows honest queue position.
"""

import json
import time
import uuid
from importlib import resources
from typing import Any

import httpx

from wire_api.providers.base import ImageResult, ResultMeta, VideoJob


def load_workflow(name: str) -> dict[str, Any]:
    ref = resources.files("wire_api.providers.local.workflows").joinpath(f"{name}.json")
    return json.loads(ref.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _fill(workflow: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Replace {{placeholder}} strings anywhere in the template."""
    text = json.dumps(workflow)
    for key, value in params.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return json.loads(text)  # type: ignore[no-any-return]


class ComfyUIImageProvider:
    provider_id = "comfyui-image"

    def __init__(self, base_url: str, workflow: str = "sdxl_image") -> None:
        self._base_url = base_url.rstrip("/")
        self._workflow = workflow

    async def generate(
        self, prompt: str, *, size: str = "1024x1024", n: int = 1, seed: int | None = None
    ) -> list[ImageResult]:
        w, h = (int(x) for x in size.split("x"))
        graph = _fill(
            load_workflow(self._workflow),
            {"prompt": json.dumps(prompt)[1:-1], "width": w, "height": h,
             "seed": seed if seed is not None else int(time.time()), "batch": n},
        )
        client_id = uuid.uuid4().hex
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=1800) as client:
            queue_resp = await client.post(
                f"{self._base_url}/prompt", json={"prompt": graph, "client_id": client_id}
            )
            queue_resp.raise_for_status()
            prompt_id = queue_resp.json()["prompt_id"]

            # poll history until the job lands
            images: list[ImageResult] = []
            while True:
                hist_resp = await client.get(f"{self._base_url}/history/{prompt_id}")
                hist_resp.raise_for_status()
                history = hist_resp.json()
                if prompt_id in history:
                    latency = (time.perf_counter() - t0) * 1000
                    outputs = history[prompt_id].get("outputs", {})
                    for node_output in outputs.values():
                        for img in node_output.get("images", []):
                            url = (
                                f"{self._base_url}/view?filename={img['filename']}"
                                f"&subfolder={img.get('subfolder', '')}&type={img.get('type', 'output')}"
                            )
                            images.append(ImageResult(
                                url=url, width=w, height=h, seed=seed,
                                meta=ResultMeta(0.0, latency, self.provider_id, self._workflow),
                            ))
                    return images
                import asyncio

                await asyncio.sleep(1.5)

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self._base_url}/system_stats")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


class ComfyUIVideoProvider:
    provider_id = "comfyui-video"

    def __init__(self, base_url: str, workflow: str = "wan_i2v") -> None:
        self._base_url = base_url.rstrip("/")
        self._workflow = workflow

    async def generate(
        self, prompt: str, *, init_image: str | None = None, duration_s: int = 5
    ) -> VideoJob:
        graph = _fill(
            load_workflow(self._workflow),
            {"prompt": json.dumps(prompt)[1:-1], "init_image": init_image or "",
             "frames": duration_s * 16, "seed": int(time.time())},
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self._base_url}/prompt",
                                     json={"prompt": graph, "client_id": uuid.uuid4().hex})
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
        return VideoJob(job_ref=prompt_id, status="queued", duration_s=duration_s,
                        meta=ResultMeta(0.0, 0, self.provider_id, self._workflow))

    async def poll(self, job_ref: str) -> VideoJob:
        async with httpx.AsyncClient(timeout=30) as client:
            hist_resp = await client.get(f"{self._base_url}/history/{job_ref}")
            hist_resp.raise_for_status()
            history = hist_resp.json()
        if job_ref not in history:
            return VideoJob(job_ref=job_ref, status="running",
                            meta=ResultMeta(0.0, 0, self.provider_id, self._workflow))
        outputs = history[job_ref].get("outputs", {})
        for node_output in outputs.values():
            for vid in node_output.get("gifs", []) + node_output.get("videos", []):
                url = f"{self._base_url}/view?filename={vid['filename']}" \
                      f"&subfolder={vid.get('subfolder', '')}&type={vid.get('type', 'output')}"
                return VideoJob(job_ref=job_ref, status="succeeded", url=url,
                                meta=ResultMeta(0.0, 0, self.provider_id, self._workflow))
        return VideoJob(job_ref=job_ref, status="failed",
                        meta=ResultMeta(0.0, 0, self.provider_id, self._workflow))

    async def healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{self._base_url}/system_stats")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
