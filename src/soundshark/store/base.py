import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from soundshark.pages import Page


@dataclass(slots=True)
class CrawlRun:
    source: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    fetched: int = 0
    from_store: int = 0
    failed: int = 0
    events: int = 0


@runtime_checkable
class RawStore(Protocol):
    async def get(self, source: str, url: str) -> Page | None: ...

    async def put(self, source: str, page: Page) -> None: ...

    def pages(self, source: str) -> AsyncIterator[Page]: ...

    async def save_run(self, run: CrawlRun) -> None: ...
