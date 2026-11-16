import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from soundshark.interfaces import PageStore
from soundshark.models import CrawlRun, Page
from soundshark.stores import FilePageStore

T0 = datetime(2026, 3, 7, 23, 59, tzinfo=ZoneInfo("Europe/Berlin"))


def make_page(url: str = "https://x.test/a", body: bytes = b"<p>hi</p>", at: datetime = T0) -> Page:
    return Page(url=url, status=200, body=body, fetched_at=at, content_type="text/html", encoding="latin-1")


def test_implements_interface(tmp_path):
    assert isinstance(FilePageStore(tmp_path), PageStore)


async def test_round_trip_keeps_bytes_and_time(tmp_path):
    store = FilePageStore(tmp_path)
    original = make_page(body=bytes(range(256)))
    await store.save_page("demo", original)
    got = await store.load_page("demo", original.url)
    assert got == original
    assert got is not None and got.fetched_at.utcoffset() == timedelta(hours=1)


async def test_missing_page_is_none(tmp_path):
    assert await FilePageStore(tmp_path).load_page("demo", "https://x.test/nope") is None


async def test_latest_copy_wins(tmp_path):
    store = FilePageStore(tmp_path)
    await store.save_page("demo", make_page(body=b"old"))
    await store.save_page("demo", make_page(body=b"new", at=T0 + timedelta(days=1)))
    got = await store.load_page("demo", "https://x.test/a")
    assert got is not None and got.body == b"new"


async def test_pages_lists_one_per_url_per_source(tmp_path):
    store = FilePageStore(tmp_path)
    await store.save_page("demo", make_page("https://x.test/a", b"1"))
    await store.save_page("demo", make_page("https://x.test/a", b"2"))
    await store.save_page("demo", make_page("https://x.test/b"))
    await store.save_page("other", make_page("https://x.test/c"))
    urls = sorted([p.url async for p in store.iter_pages("demo")])
    assert urls == ["https://x.test/a", "https://x.test/b"]
    assert [p async for p in store.iter_pages("never-crawled")] == []


async def test_save_run_overwrites_same_id(tmp_path):
    store = FilePageStore(tmp_path)
    run = CrawlRun("demo")
    await store.save_run(run)
    run.pages_fetched = 5
    run.finished_at = datetime.now(UTC)
    await store.save_run(run)
    files = list((tmp_path / "runs" / "demo").iterdir())
    assert [f.name for f in files] == [f"{run.id}.json"]
    record = json.loads(files[0].read_text())
    assert record["pages_fetched"] == 5
    assert datetime.fromisoformat(record["finished_at"]) == run.finished_at


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "../etc", "a b", "-x", "x" * 65])
async def test_rejects_unsafe_source_names(tmp_path, bad):
    store = FilePageStore(tmp_path)
    with pytest.raises(ValueError):
        await store.save_page(bad, make_page())
    with pytest.raises(ValueError):
        await store.load_page(bad, "https://x.test/a")
    with pytest.raises(ValueError):
        await store.save_run(CrawlRun(bad))


async def test_rejects_unsafe_run_id(tmp_path):
    with pytest.raises(ValueError):
        await FilePageStore(tmp_path).save_run(CrawlRun("demo", id="../x"))


async def test_no_temp_files_left_behind(tmp_path):
    store = FilePageStore(tmp_path)
    for i in range(3):
        await store.save_page("demo", make_page(f"https://x.test/{i}"))
    await store.save_run(CrawlRun("demo"))
    leftovers = [p for p in tmp_path.rglob("*") if p.name.startswith(".") or p.suffix == ".tmp"]
    assert leftovers == []
