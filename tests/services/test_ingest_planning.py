from datetime import UTC, datetime, timedelta

from soundshark.models import Event, Page
from soundshark.services.credits import choose_new_artist_slugs
from soundshark.services.ingest import PageWithEvents, latest_copy_of_each_event, plan_lineup_slots
from soundshark.utils.slugs import slugify

T0 = datetime(2026, 3, 7, 23, 0, tzinfo=UTC)


def make_event(source_id: str = "e1", **rooms: list[str]) -> Event:
    return Event(source="fake", source_id=source_id, starts_at=T0, venue="V", city="C", rooms=rooms)


def make_page(url: str, at: datetime = T0) -> Page:
    return Page(url=url, status=200, body=b"", fetched_at=at)


def test_slots_keep_room_position_and_raw_text():
    slots = plan_lineup_slots(make_event(Main=["Ora Vance", "Mirek Sol (live)"], Annex=["Juno Hale"]))
    assert [(s.room, s.position, s.raw_text) for s in slots] == [
        ("Main", 0, "Ora Vance"),
        ("Main", 1, "Mirek Sol (live)"),
        ("Annex", 0, "Juno Hale"),
    ]
    assert slots[1].tags == ["live"]


def test_b2b_slot_is_marked_b2b():
    [slot] = plan_lineup_slots(make_event(Main=["Ora Vance b2b Juno Hale"]))
    assert slot.is_b2b


def test_duo_with_ampersand_is_not_b2b():
    [slot] = plan_lineup_slots(make_event(Main=["Ora Vance & Juno Hale"]))
    assert not slot.is_b2b


def test_event_seen_on_two_pages_keeps_the_newest_copy():
    old = PageWithEvents(make_page("https://x.test/old", T0), [make_event("e1", Main=["Old"])])
    new = PageWithEvents(
        make_page("https://x.test/new", T0 + timedelta(days=1)), [make_event("e1", Main=["New"])]
    )
    latest = latest_copy_of_each_event([new, old])
    event, page = latest["e1"]
    assert event.rooms == {"Main": ["New"]}
    assert page.url == "https://x.test/new"


def test_slugs_are_readable_and_never_collide():
    slugs = choose_new_artist_slugs(
        ["ora vance", "ora-vance", "möwe fan", "!!!"], slugs_already_taken={"juno-hale"}
    )
    assert slugs["ora vance"] == "ora-vance"
    assert slugs["ora-vance"].startswith("ora-vance-")
    assert slugs["möwe fan"] == "mowe-fan"
    assert slugs["!!!"].startswith("x-")
    assert len(set(slugs.values())) == 4


def test_slug_already_in_the_database_gets_a_suffix():
    assert choose_new_artist_slugs(["juno hale"], {"juno-hale"})["juno hale"].startswith("juno-hale-")


def test_slugify():
    assert slugify("Möwe Fan (live)") == "mowe-fan-live"
