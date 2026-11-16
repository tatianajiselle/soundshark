import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from soundshark.pages import Page
from soundshark.store import CrawlRun, FileStore, RawStore

T0 = datetime(2026, 3, 7, 23, 59, tzinfo=ZoneInfo("Europe/Berlin"))


def page(url: str = "https://x.test/a", body: bytes = b"<p>hi</p>", at: datetime = T0) -> Page:
    return Page(url=url, status=200, body=body, fetched_at=at, content_type="text/html", encoding="latin-1")


def test_implements_interface(tmp_path):
    assert isinstance(FileStore(tmp_path), RawStore)


async def test_round_trip_keeps_bytes_and_time(tmp_path):
    store = FileStore(tmp_path)
    original = page(body=bytes(range(256)))
    await store.put("demo", original)
    got = await store.get("demo", original.url)
    assert got == original
    assert got is not None and got.fetched_at.utcoffset() == timedelta(hours=1)


async def test_missing_page_is_none(tmp_path):
    assert await FileStore(tmp_path).get("demo", "https://x.test/nope") is None


async def test_latest_copy_wins(tmp_path):
    store = FileStore(tmp_path)
    await store.put("demo", page(body=b"old"))
    await store.put("demo", page(body=b"new", at=T0 + timedelta(days=1)))
    got = await store.get("demo", "https://x.test/a")
    assert got is not None and got.body == b"new"


async def test_pages_lists_one_per_url_per_source(tmp_path):
    store = FileStore(tmp_path)
    await store.put("demo", page("https://x.test/a", b"1"))
    await store.put("demo", page("https://x.test/a", b"2"))
    await store.put("demo", page("https://x.test/b"))
    await store.put("other", page("https://x.test/c"))
    urls = sorted([p.url async for p in store.pages("demo")])
    assert urls == ["https://x.test/a", "https://x.test/b"]
    assert [p async for p in store.pages("never-crawled")] == []


async def test_save_run_overwrites_same_id(tmp_path):
    store = FileStore(tmp_path)
    run = CrawlRun("demo")
    await store.save_run(run)
    run.fetched = 5
    run.finished_at = datetime.now(UTC)
    await store.save_run(run)
    files = list((tmp_path / "runs" / "demo").iterdir())
    assert [f.name for f in files] == [f"{run.id}.json"]
    record = json.loads(files[0].read_text())
    assert record["fetched"] == 5
    assert datetime.fromisoformat(record["finished_at"]) == run.finished_at


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "../etc", "a b", "-x", "x" * 65])
async def test_rejects_unsafe_source_names(tmp_path, bad):
    store = FileStore(tmp_path)
    with pytest.raises(ValueError):
        await store.put(bad, page())
    with pytest.raises(ValueError):
        await store.get(bad, "https://x.test/a")
    with pytest.raises(ValueError):
        await store.save_run(CrawlRun(bad))


async def test_rejects_unsafe_run_id(tmp_path):
    with pytest.raises(ValueError):
        await FileStore(tmp_path).save_run(CrawlRun("demo", id="../x"))


async def test_no_temp_files_left_behind(tmp_path):
    store = FileStore(tmp_path)
    for i in range(3):
        await store.put("demo", page(f"https://x.test/{i}"))
    await store.save_run(CrawlRun("demo"))
    leftovers = [p for p in tmp_path.rglob("*") if p.name.startswith(".") or p.suffix == ".tmp"]
    assert leftovers == []
