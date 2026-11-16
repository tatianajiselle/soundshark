"""A demo source on a made-up website, so anyone can run SoundShark end to end without real data.

The site is served in-process by an httpx.MockTransport, so the demo never touches the network.
Every artist, venue and event here is fictional.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from soundshark.models import Event
from soundshark.pages import Page, Parsed
from soundshark.sources.base import Politeness

BASE = "https://demo.soundshark.test"
_TZ = ZoneInfo("Europe/Berlin")

_EVENTS = {
    "2026-03": [
        {
            "id": "d1",
            "starts": "2026-03-06 23:00",
            "venue": "Kelvin Hall",
            "city": "Lakeport",
            "rooms": {
                "Main": ["Ora Vance", "Mirek Sol", "Tamsin Rook"],
                "Annex": ["Juno Hale", "Petra Ilse"],
            },
        },
        {
            "id": "d2",
            "starts": "2026-03-13 23:00",
            "venue": "Kelvin Hall",
            "city": "Lakeport",
            "rooms": {"Main": ["Mirek Sol", "Dax Ferro"], "Annex": ["Ora Vance b2b Juno Hale"]},
        },
    ],
    "2026-04": [
        {
            "id": "d3",
            "starts": "2026-04-02 22:00",
            "venue": "The Cistern",
            "city": "Northvale",
            "rooms": {"Main": ["Tamsin Rook", "Dax Ferro", "Selene Mau"]},
        },
        {
            "id": "d4",
            "starts": "2026-04-18 22:00",
            "venue": "The Cistern",
            "city": "Northvale",
            "rooms": {"Main": ["Petra Ilse", "Selene Mau"], "Basement": ["Quill Arden"]},
        },
    ],
}

_PAGES: dict[str, dict] = {
    "/": {"links": [f"{BASE}/{month}/" for month in _EVENTS]},
    **{f"/{month}/": {"links": [f"{BASE}/"], "events": events} for month, events in _EVENTS.items()},
}


def _serve(request: httpx.Request) -> httpx.Response:
    page = _PAGES.get(request.url.path)
    if page is None:
        return httpx.Response(404)
    return httpx.Response(200, json=page)


class DemoSource:
    name = "demo"
    seeds = (f"{BASE}/",)

    def __init__(self, min_interval: float = 0.05) -> None:
        self.politeness = Politeness(min_interval=min_interval, max_in_flight=2)
        self.transport = httpx.MockTransport(_serve)

    def parse(self, page: Page) -> Parsed:
        data = json.loads(page.text)
        events = [
            Event(
                source=self.name,
                source_id=item["id"],
                starts_at=datetime.strptime(item["starts"], "%Y-%m-%d %H:%M").replace(tzinfo=_TZ),
                venue=item["venue"],
                city=item["city"],
                rooms=item["rooms"],
                url=page.url,
            )
            for item in data.get("events", [])
        ]
        return Parsed(events=events, links=data.get("links", []))

    def refresh_after(self, url: str) -> timedelta | None:
        return timedelta(days=1) if url == f"{BASE}/" else None
