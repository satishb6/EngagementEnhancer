"""SourceAdapter — the common interface every ingestion adapter implements."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from wire_api.models import Source


@dataclass
class FetchedItem:
    canonical_url: str
    title: str
    body: str
    domain: str
    author: str = ""
    published_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Hash of normalised content — unchanged items cost nothing downstream."""
        basis = f"{self.canonical_url}\n{self.title}\n{self.body[:2000]}"
        return hashlib.sha256(basis.encode()).hexdigest()


@dataclass
class FetchResult:
    items: list[FetchedItem]
    items_fetched: int
    quota_consumed: int = 0
    http_status: int = 200
    etag: str = ""
    last_modified: str = ""
    not_modified: bool = False


@runtime_checkable
class SourceAdapter(Protocol):
    kind: str

    async def fetch(self, source: Source) -> FetchResult: ...
