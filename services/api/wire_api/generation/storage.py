"""Artifact storage: S3-compatible when configured, local disk in dev."""

import asyncio
from pathlib import Path

import httpx

from wire_api.models.base import uuid7
from wire_api.settings import get_settings

LOCAL_ROOT = Path("storage")


async def save_bytes(data: bytes, suffix: str) -> str:
    """Persist bytes, return a storage URI (s3://bucket/key or file path)."""
    settings = get_settings()
    key = f"artifacts/{uuid7().hex}{suffix}"
    if settings.s3_endpoint_url and settings.s3_access_key_id:
        import boto3

        def _put() -> None:
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region,
            )
            client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data)

        await asyncio.to_thread(_put)
        return f"s3://{settings.s3_bucket}/{key}"

    path = LOCAL_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


async def mirror_url(url: str, suffix: str) -> str:
    """Download a provider-hosted result into our storage before its
    short-lived URL expires."""
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return await save_bytes(resp.content, suffix)


async def delete_uri(uri: str) -> None:
    settings = get_settings()
    if uri.startswith("s3://"):
        import boto3

        _, _, rest = uri.partition("s3://")
        bucket, _, key = rest.partition("/")

        def _delete() -> None:
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region,
            )
            client.delete_object(Bucket=bucket, Key=key)

        await asyncio.to_thread(_delete)
        return
    path = Path(uri)
    if path.exists():
        path.unlink()
