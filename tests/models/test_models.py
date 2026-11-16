from datetime import UTC, datetime

import pytest

from soundshark.models import CrawlRun, Event, Page


def test_page_text_decodes_the_body():
    page = Page(url="https://x.test/", status=200, body="Säule".encode(), fetched_at=datetime.now(UTC))
    assert page.text == "Säule"


def test_page_requires_a_timezone_aware_fetch_time():
    with pytest.raises(ValueError):
        Page(url="https://x.test/", status=200, body=b"", fetched_at=datetime(2026, 1, 1))


def test_event_requires_a_timezone_aware_start():
    with pytest.raises(ValueError):
        Event(source="x", source_id="1", starts_at=datetime(2026, 1, 1), venue="V", city="C")


def test_event_artists_are_unique_across_rooms_in_order():
    event = Event(
        source="x",
        source_id="1",
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        venue="V",
        city="C",
        rooms={"Main": ["Ora Vance", "Mirek Sol"], "Annex": ["Mirek Sol", "Juno Hale"]},
    )
    assert event.artists == ["Ora Vance", "Mirek Sol", "Juno Hale"]


def test_each_crawl_run_gets_its_own_id():
    assert CrawlRun("demo").id != CrawlRun("demo").id
