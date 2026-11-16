import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_COUNTRY_CODE = re.compile(r"[A-Z]{2}")


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
    venue_country_code: str | None = None
    venue_timezone: str | None = None

    def __post_init__(self) -> None:
        for name, value in (("starts_at", self.starts_at), ("ends_at", self.ends_at)):
            if value is not None and value.tzinfo is None:
                raise ValueError(f"Event.{name} must be timezone-aware (got {value!r})")
        if self.venue_country_code is not None and not _COUNTRY_CODE.fullmatch(self.venue_country_code):
            raise ValueError(
                f"Event.venue_country_code must be two capital letters (got {self.venue_country_code!r})"
            )
        if self.venue_timezone is not None:
            try:
                ZoneInfo(self.venue_timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError(
                    f"Event.venue_timezone {self.venue_timezone!r} is not a known time zone"
                ) from error

    @property
    def artists(self) -> list[str]:
        unique_in_order: dict[str, None] = {}
        for lineup in self.rooms.values():
            for name in lineup:
                unique_in_order.setdefault(name, None)
        return list(unique_in_order)
