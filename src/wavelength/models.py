"""The shapes every source produces. The engine and graph only ever see these."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Event:
    source: str  # which Source produced it, e.g. "demo"
    source_id: str  # the source's own ID for this event
    starts_at: datetime
    venue: str
    city: str
    # room/stage -> artists on it, in billing order. Same room = stronger link.
    rooms: dict[str, list[str]] = field(default_factory=dict)
    ends_at: datetime | None = None
    title: str | None = None
    url: str | None = None
    # Cross-source match key (e.g. an RA event ID) when a source provides one.
    ra_id: str | None = None

    @property
    def artists(self) -> list[str]:
        """Everyone on the bill, across all rooms, without duplicates."""
        seen: dict[str, None] = {}
        for lineup in self.rooms.values():
            for name in lineup:
                seen.setdefault(name, None)
        return list(seen)
