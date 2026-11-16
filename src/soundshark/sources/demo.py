import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

import httpx

from soundshark.models import Event

_SAMPLE = [
    (
        "d1",
        "2026-03-06 23:00",
        "Kelvin Hall",
        "Lakeport",
        {
            "Main": ["Ora Vance", "Mirek Sol", "Tamsin Rook"],
            "Annex": ["Juno Hale", "Petra Ilse"],
        },
    ),
    (
        "d2",
        "2026-03-13 23:00",
        "Kelvin Hall",
        "Lakeport",
        {
            "Main": ["Mirek Sol", "Dax Ferro"],
            "Annex": ["Ora Vance b2b Juno Hale"],
        },
    ),
    (
        "d3",
        "2026-04-02 22:00",
        "The Cistern",
        "Northvale",
        {
            "Main": ["Tamsin Rook", "Dax Ferro", "Selene Mau"],
        },
    ),
    (
        "d4",
        "2026-04-18 22:00",
        "The Cistern",
        "Northvale",
        {
            "Main": ["Petra Ilse", "Selene Mau"],
            "Basement": ["Quill Arden"],
        },
    ),
]


class DemoSource:
    name = "demo"

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay

    async def events(self, client: httpx.AsyncClient) -> AsyncIterator[Event]:
        for source_id, starts, venue, city, rooms in _SAMPLE:
            await asyncio.sleep(self.delay)
            yield Event(
                source=self.name,
                source_id=source_id,
                starts_at=datetime.strptime(starts, "%Y-%m-%d %H:%M"),
                venue=venue,
                city=city,
                rooms=rooms,
            )
