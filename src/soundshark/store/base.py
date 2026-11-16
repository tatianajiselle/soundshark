"""The raw store: every fetched page is kept so it can be parsed again without refetching.

Implementations: files on disk now, Postgres later. The engine only sees this interface.
"""

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
    async def get(self, source: str, url: str) -> Page | None:
        """The latest stored copy of this URL, or None if it was never stored."""
        ...

    async def put(self, source: str, page: Page) -> None:
        """Store a page, replacing any earlier copy of the same URL."""
        ...

    def pages(self, source: str) -> AsyncIterator[Page]:
        """Every stored page of a source (latest copy per URL), for re-parsing. An async generator."""
        ...

    async def save_run(self, run: CrawlRun) -> None:
        """Record a crawl run. Saving the same run id again overwrites it."""
        ...
