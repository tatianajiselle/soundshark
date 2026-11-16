from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Event:
    source: str
    source_id: str
    starts_at: datetime
    venue: str
    city: str
    rooms: dict[str, list[str]] = field(default_factory=dict)
    ends_at: datetime | None = None
    title: str | None = None
    url: str | None = None
    ra_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("starts_at", self.starts_at), ("ends_at", self.ends_at)):
            if value is not None and value.tzinfo is None:
                raise ValueError(f"Event.{name} must be timezone-aware (got {value!r})")

    @property
    def artists(self) -> list[str]:
        seen: dict[str, None] = {}
        for lineup in self.rooms.values():
            for name in lineup:
                seen.setdefault(name, None)
        return list(seen)
