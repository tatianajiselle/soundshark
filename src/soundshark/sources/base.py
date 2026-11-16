from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, runtime_checkable

from soundshark.pages import Page, Parsed

DEFAULT_USER_AGENT = "soundshark/0.1 (+https://soundshark.dev)"


@dataclass(frozen=True, slots=True)
class Politeness:
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
    def seeds(self) -> Sequence[str]: ...

    def parse(self, page: Page) -> Parsed: ...

    def refresh_after(self, url: str) -> timedelta | None: ...
