"""fal.ai adapters — image and video behind one API with queue + webhooks."""

import time

import httpx

from wire_api.providers.base import ImageResult, ResultMeta, VideoJob
from wire_api.providers.costs import IMAGE_CENTS, VIDEO_CENTS_PER_SECOND

QUEUE_URL = "https://queue.fal.run"
IMAGE_MODEL = "fal-ai/flux/dev"
VIDEO_MODEL = "fal-ai/kling-video/v1.6/standard/image-to-video"


class FalImageProvider:
    provider_id = "fal-image"

    def __init__(self, api_key: str, model_path: str = IMAGE_MODEL) -> None:
        self._api_key = api_key
        self._model_path = model_path

    async def generate(
        self, prompt: str, *, size: str = "1024x1024", n: int = 1, seed: int | None = None
    ) -> list[ImageResult]:
        w, h = (int(x) for x in size.split("x"))
        body: dict[str, object] = {
            "prompt": prompt,
            "image_size": {"width": w, "height": h},
            "num_images": n,
        }
        if seed is not None:
            body["seed"] = seed

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=300) as client:
            # sync-mode convenience endpoint; the orchestrator wraps this in a job
            resp = await client.post(
                f"https://fal.run/{self._model_path}",
                json=body,
                headers={"Authorization": f"Key {self._api_key}"},
            )
            resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        unit_cost = IMAGE_CENTS.get("fal-flux-dev", 2.5)
        return [
            ImageResult(
                url=img["url"],
                width=img.get("width", w),
                height=img.get("height", h),
                seed=data.get("seed"),
                meta=ResultMeta(unit_cost, latency, self.provider_id, self._model_path),
            )
            for img in data.get("images", [])
        ]

    async def healthy(self) -> bool:
        return bool(self._api_key)


class FalVideoProvider:
    provider_id = "fal-video"

    def __init__(self, api_key: str, model_path: str = VIDEO_MODEL) -> None:
        self._api_key = api_key
        self._model_path = model_path

    async def generate(
        self, prompt: str, *, init_image: str | None = None, duration_s: int = 5
    ) -> VideoJob:
        body: dict[str, object] = {"prompt": prompt, "duration": str(duration_s)}
        if init_image:
            body["image_url"] = init_image
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{QUEUE_URL}/{self._model_path}",
                json=body,
                headers={"Authorization": f"Key {self._api_key}"},
            )
            resp.raise_for_status()
        data = resp.json()
        cost = VIDEO_CENTS_PER_SECOND["fal-kling-video"] * duration_s
        return VideoJob(
            job_ref=data["request_id"],
            status="queued",
            duration_s=duration_s,
            meta=ResultMeta(cost, 0, self.provider_id, self._model_path),
        )

    async def poll(self, job_ref: str) -> VideoJob:
        async with httpx.AsyncClient(timeout=60) as client:
            status_resp = await client.get(
                f"{QUEUE_URL}/{self._model_path}/requests/{job_ref}/status",
                headers={"Authorization": f"Key {self._api_key}"},
            )
            status_resp.raise_for_status()
            status = status_resp.json()
            state = status.get("status", "")
            if state != "COMPLETED":
                mapped = "running" if state in ("IN_PROGRESS", "IN_QUEUE") else "failed"
                return VideoJob(job_ref=job_ref, status=mapped,
                                meta=ResultMeta(0, 0, self.provider_id, self._model_path))
            result_resp = await client.get(
                f"{QUEUE_URL}/{self._model_path}/requests/{job_ref}",
                headers={"Authorization": f"Key {self._api_key}"},
            )
            result_resp.raise_for_status()
            data = result_resp.json()
        video = data.get("video", {})
        return VideoJob(
            job_ref=job_ref,
            status="succeeded",
            url=video.get("url", ""),
            meta=ResultMeta(0, 0, self.provider_id, self._model_path),
        )

    async def healthy(self) -> bool:
        return bool(self._api_key)
