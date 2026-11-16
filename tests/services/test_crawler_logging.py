import httpx
from structlog.testing import capture_logs
from structlog.typing import EventDict

from tests.fakes import FakeSite, FakeSource, crawl_fake_site, fake_url

EXAMPLE_SITE = {"A": ["B", "C"], "B": [], "C": []}


def events_named(logs: list[EventDict], name: str) -> list[EventDict]:
    return [entry for entry in logs if entry["event"] == name]


async def test_every_line_carries_source_and_run_id():
    with capture_logs() as logs:
        result = await crawl_fake_site(FakeSite(EXAMPLE_SITE))
    assert logs
    assert all(entry["source"] == "fake" and entry["run_id"] == result.run.id for entry in logs)


async def test_logs_start_and_finish_with_counts():
    with capture_logs() as logs:
        await crawl_fake_site(FakeSite(EXAMPLE_SITE), max_pages=50)
    assert logs[0]["event"] == "crawl.started"
    assert logs[0]["seed_urls"] == [fake_url("A")]
    assert logs[0]["max_pages"] == 50
    finished = logs[-1]
    assert finished["event"] == "crawl.finished"
    assert finished["pages_fetched"] == 3
    assert finished["events_found"] == 3
    assert finished["pages_failed"] == 0
    assert "duration_seconds" in finished


async def test_logs_each_retry_then_success():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(503), lambda: httpx.Response(500))
    with capture_logs() as logs:
        await crawl_fake_site(site)
    retries = events_named(logs, "http.retrying")
    assert [(r["attempt"], r["reason"]) for r in retries] == [(1, "status 503"), (2, "status 500")]
    assert all(r["url"] == fake_url("A") and r["log_level"] == "info" for r in retries)
    assert events_named(logs, "http.gave_up") == []


async def test_logs_giving_up_with_the_last_reason():
    site = FakeSite({"A": []})
    site.script("A", *[lambda: httpx.Response(503)] * 5)
    with capture_logs() as logs:
        await crawl_fake_site(site, FakeSource(max_retries=1))
    [gave_up] = events_named(logs, "http.gave_up")
    assert gave_up["attempts"] == 2
    assert gave_up["reason"] == "status 503"
    assert gave_up["log_level"] == "warning"


async def test_logs_missing_pages_with_their_status():
    with capture_logs() as logs:
        await crawl_fake_site(FakeSite({"A": ["missing"]}))
    [missing] = events_named(logs, "http.unexpected_status")
    assert missing["url"] == fake_url("missing")
    assert missing["status"] == 404


async def test_logs_parse_failures_as_errors_with_the_exception():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(200, json={"unparseable": True}))
    with capture_logs() as logs:
        await crawl_fake_site(site)
    [failure] = events_named(logs, "page.parse_failed")
    assert failure["url"] == fake_url("A")
    assert failure["log_level"] == "error"
    assert failure["exc_info"] is True


async def test_logs_robots_blocks_and_robots_load():
    site = FakeSite(EXAMPLE_SITE, robots_txt="User-agent: *\nDisallow: /C\n")
    with capture_logs() as logs:
        await crawl_fake_site(site)
    [loaded] = events_named(logs, "robots.loaded")
    assert loaded["origin"] == "https://site.test"
    [blocked] = events_named(logs, "page.blocked_by_robots")
    assert blocked["url"] == fake_url("C")
    assert blocked["depth"] == 1
