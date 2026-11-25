import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from soundshark.models import CrawlRun, Event, Page


def test_page_text_decodes_the_body():
    page = Page(url="https://x.test/", status=200, body="Möwe".encode(), fetched_at=datetime.now(UTC))
    assert page.text == "Möwe"


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


def test_page_content_hash_identifies_the_body():
    page = Page(url="https://x.test/", status=200, body=b"abc", fetched_at=datetime.now(UTC))
    assert page.content_sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_page_hashes_its_body_once(monkeypatch):
    calls = []
    real = hashlib.sha256
    monkeypatch.setattr(hashlib, "sha256", lambda data: calls.append(data) or real(data))
    page = Page(url="https://x.test/", status=200, body=b"abc", fetched_at=datetime(2026, 1, 1, tzinfo=UTC))
    for _ in range(3):
        assert page.content_sha256 == real(b"abc").hexdigest()
    assert len(calls) == 1


def test_page_hash_follows_the_body_through_replace():
    page = Page(url="https://x.test/", status=200, body=b"abc", fetched_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert replace(page, body=b"xyz").content_sha256 == hashlib.sha256(b"xyz").hexdigest()
    assert replace(page, body=b"xyz") != page
    assert replace(page, url="https://x.test/") == page


@pytest.mark.parametrize("bad_code", ["de", "DEU", "D1"])
def test_event_venue_country_must_be_two_capital_letters(bad_code):
    with pytest.raises(ValueError):
        Event(
            source="x",
            source_id="1",
            starts_at=datetime.now(UTC),
            venue="V",
            city="C",
            venue_country_code=bad_code,
        )


def test_event_venue_timezone_must_exist():
    with pytest.raises(ValueError):
        Event(
            source="x",
            source_id="1",
            starts_at=datetime.now(UTC),
            venue="V",
            city="C",
            venue_timezone="Mars/Base",
        )
