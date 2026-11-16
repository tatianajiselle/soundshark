from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from soundshark.models import CrawlRun, Page


@runtime_checkable
class PageStore(Protocol):
    async def load_page(self, source_name: str, url: str) -> Page | None: ...

    async def save_page(self, source_name: str, page: Page) -> None: ...

    def iter_pages(self, source_name: str) -> AsyncIterator[Page]: ...

    async def save_run(self, run: CrawlRun) -> None: ...
