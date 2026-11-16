import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from soundshark.models.event import Event


def _new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def _now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CrawlRun:
    source_name: str
    id: str = field(default_factory=_new_run_id)
    started_at: datetime = field(default_factory=_now_utc)
    finished_at: datetime | None = None
    pages_fetched: int = 0
    pages_from_store: int = 0
    pages_failed: int = 0
    pages_blocked_by_robots: int = 0
    events_found: int = 0
    error: str | None = None


@dataclass(slots=True)
class CrawlResult:
    events: list[Event]
    visited_urls: set[str]
    run: CrawlRun
