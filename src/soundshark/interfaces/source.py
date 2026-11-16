from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol, runtime_checkable

from soundshark.models import CrawlPolicy, Page, ParsedPage


@runtime_checkable
class Source(Protocol):
    name: str
    crawl_policy: CrawlPolicy

    @property
    def seed_urls(self) -> Sequence[str]: ...

    def parse(self, page: Page) -> ParsedPage: ...

    def refetch_after(self, url: str) -> timedelta | None: ...
