import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from soundshark.models import CrawlPolicy, Event, Page, ParsedPage

DEMO_SITE_URL = "https://demo.soundshark.test"
_DEMO_TIMEZONE = ZoneInfo("Europe/Berlin")

_DEMO_EVENTS_BY_MONTH = {
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

_DEMO_PAGES_BY_PATH: dict[str, dict] = {
    "/": {"links": [f"{DEMO_SITE_URL}/{month}/" for month in _DEMO_EVENTS_BY_MONTH]},
    **{
        f"/{month}/": {"links": [f"{DEMO_SITE_URL}/"], "events": events}
        for month, events in _DEMO_EVENTS_BY_MONTH.items()
    },
}


def _serve_demo_page(request: httpx.Request) -> httpx.Response:
    demo_page = _DEMO_PAGES_BY_PATH.get(request.url.path)
    if demo_page is None:
        return httpx.Response(404)
    return httpx.Response(200, json=demo_page)


class DemoSource:
    name = "demo"
    seed_urls = (f"{DEMO_SITE_URL}/",)

    def __init__(self, seconds_between_requests: float = 0.05) -> None:
        self.crawl_policy = CrawlPolicy(
            seconds_between_requests_per_host=seconds_between_requests, max_concurrent_requests_per_host=2
        )
        self.http_transport = httpx.MockTransport(_serve_demo_page)

    def parse(self, page: Page) -> ParsedPage:
        demo_page = json.loads(page.text)
        events = [
            Event(
                source=self.name,
                source_id=item["id"],
                starts_at=datetime.strptime(item["starts"], "%Y-%m-%d %H:%M").replace(tzinfo=_DEMO_TIMEZONE),
                venue=item["venue"],
                city=item["city"],
                rooms=item["rooms"],
                url=page.url,
                venue_timezone="Europe/Berlin",
            )
            for item in demo_page.get("events", [])
        ]
        return ParsedPage(events=events, links_to_follow=demo_page.get("links", []))

    def refetch_after(self, url: str) -> timedelta | None:
        return timedelta(days=1) if url == f"{DEMO_SITE_URL}/" else None
