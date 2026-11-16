import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from soundshark.models.event import Event


@dataclass(frozen=True, slots=True)
class Page:
    url: str
    status: int
    body: bytes
    fetched_at: datetime
    content_type: str | None = None
    encoding: str = "utf-8"
    crawl_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("Page.fetched_at must be timezone-aware")

    @property
    def text(self) -> str:
        return self.body.decode(self.encoding, errors="replace")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredPageVersion:
    page: Page
    storage_path: str
    is_latest: bool


@dataclass(slots=True)
class ParsedPage:
    events: list[Event] = field(default_factory=list)
    links_to_follow: list[str] = field(default_factory=list)
