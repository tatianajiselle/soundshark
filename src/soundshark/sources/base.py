"""The Source interface: what every data source must provide.

The engine (soundshark/crawler.py) does all fetching, pacing, robots.txt, retries and storage.
A source only says where to start, how polite to be, and what a fetched page means.

Real, site-specific sources live in a separate private package and are loaded at runtime
(see loader.py). This public repo only ships the interface and a demo.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, runtime_checkable

from soundshark.pages import Page, Parsed

DEFAULT_USER_AGENT = "soundshark/0.1 (+https://soundshark.dev)"


@dataclass(frozen=True, slots=True)
class Politeness:
    """How hard the engine may hit a source's site. min_interval is the gap between request starts per host;
    a robots.txt Crawl-delay that asks for more wins."""

    user_agent: str = DEFAULT_USER_AGENT
    max_in_flight: int = 1
    min_interval: float = 2.0
    max_retries: int = 3
    backoff: float = 1.0
    max_retry_after: float = 300.0
    timeout: float = 20.0


@runtime_checkable
class Source(Protocol):
    name: str
    politeness: Politeness

    @property
    def seeds(self) -> Sequence[str]:
        """Where the crawl starts (depth 0)."""
        ...

    def parse(self, page: Page) -> Parsed:
        """The events on this page and the links worth following from it (absolute URLs)."""
        ...

    def refresh_after(self, url: str) -> timedelta | None:
        """How old a stored copy of this URL may get before it's fetched again. None: never refetch."""
        ...
