import asyncio
from collections import deque
from datetime import timedelta

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from soundshark.interfaces import PageStore
from soundshark.services import crawl
from tests.fakes import FakeSite, FakeSource, InMemoryPageStore, crawl_fake_site, fake_url

EXAMPLE_SITE = {"A": ["B", "C"], "B": ["C", "D"], "C": ["A"], "D": ["E"], "E": []}


@pytest.mark.parametrize(
    ("max_depth", "expected_pages"), [(0, "A"), (1, "ABC"), (2, "ABCD"), (None, "ABCDE")]
)
async def test_bfs_stops_at_max_depth(max_depth, expected_pages):
    site = FakeSite(EXAMPLE_SITE)
    result = await crawl_fake_site(site, max_depth=max_depth)
    assert result.visited_urls == {fake_url(page) for page in expected_pages}
    assert site.fetched_page_names() == set(expected_pages)


async def test_never_fetches_a_url_twice():
    every_page_links_to_every_other = {page: [p for p in "ABCDEF" if p != page] for page in "ABCDEF"}
    site = FakeSite(every_page_links_to_every_other)
    await crawl_fake_site(site, FakeSource(max_concurrent_requests_per_host=4))
    assert all(count == 1 for count in site.requests_per_path.values())


async def test_max_pages_caps_fetches():
    wide_site = {str(i): [str(i * 3 + k) for k in (1, 2, 3)] for i in range(50)}
    site = FakeSite(wide_site)
    source = FakeSource(seed_pages=("0",), max_concurrent_requests_per_host=3)
    result = await crawl_fake_site(site, source, max_pages=5)
    assert len(result.visited_urls) == 5
    assert len(site.fetched_page_names()) == 5


async def test_collects_events_and_counts_the_run():
    result = await crawl_fake_site(FakeSite(EXAMPLE_SITE))
    assert len(result.events) == 5
    assert result.run.pages_fetched == 5
    assert result.run.events_found == 5
    assert result.run.finished_at is not None


async def test_unreachable_site_returns_quickly_without_events():
    def refuse_connection(request):
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse_connection)) as http_client:
        async with asyncio.timeout(5):
            result = await crawl(FakeSource(max_retries=2), http_client)
    assert result.events == []
    assert result.visited_urls == {fake_url("A")}
    assert result.run.pages_fetched == 0


async def test_missing_and_unparseable_pages_are_skipped():
    site = FakeSite({"A": ["B", "C", "missing"], "B": [], "C": []})
    site.script("B", lambda: httpx.Response(200, json={"unparseable": True}))
    result = await crawl_fake_site(site)
    assert result.run.pages_fetched == 3
    assert result.run.pages_failed == 2
    assert {event.source_id for event in result.events} == {fake_url("A"), fake_url("C")}


async def test_robots_disallowed_pages_are_counted_not_fetched():
    site = FakeSite(EXAMPLE_SITE, robots_txt="User-agent: *\nDisallow: /C\n")
    result = await crawl_fake_site(site)
    assert "C" not in site.fetched_page_names()
    assert result.run.pages_blocked_by_robots == 1


async def test_stored_pages_are_reused_instead_of_refetched():
    store = InMemoryPageStore()
    assert isinstance(store, PageStore)
    first = await crawl_fake_site(FakeSite(EXAMPLE_SITE), page_store=store)
    site_on_second_visit = FakeSite(EXAMPLE_SITE)
    second = await crawl_fake_site(site_on_second_visit, page_store=store)
    assert first.run.pages_fetched == 5
    assert second.run.pages_from_store == 5
    assert site_on_second_visit.fetched_page_names() == set()
    assert len(second.events) == 5
    assert len(store.saved_runs) == 2


async def test_stale_stored_pages_are_refetched():
    store = InMemoryPageStore()
    await crawl_fake_site(FakeSite(EXAMPLE_SITE), page_store=store)
    always_stale = FakeSource(refetch_after=timedelta(0))
    second = await crawl_fake_site(FakeSite(EXAMPLE_SITE), always_stale, page_store=store)
    assert second.run.pages_fetched == 5


async def test_respects_max_concurrent_requests_per_host():
    hub_and_spokes = {"A": [str(i) for i in range(12)], **{str(i): [] for i in range(12)}}
    site = FakeSite(hub_and_spokes)
    site.response_delay_seconds = 0.02
    await crawl_fake_site(site, FakeSource(max_concurrent_requests_per_host=3))
    assert site.peak_concurrent_requests == 3


def sequential_bfs(links_by_page: dict[str, list[str]], seed: str, max_depth: int | None) -> set[str]:
    seen, frontier = {seed}, deque([(seed, 0)])
    while frontier:
        page, depth = frontier.popleft()
        if page not in links_by_page or (max_depth is not None and depth >= max_depth):
            continue
        for link in links_by_page[page]:
            if link not in seen:
                seen.add(link)
                frontier.append((link, depth + 1))
    return seen


page_names = st.sampled_from([str(i) for i in range(12)])


@settings(max_examples=60, deadline=None)
@given(
    links_by_page=st.dictionaries(page_names, st.lists(page_names, max_size=5), min_size=1),
    max_depth=st.none() | st.integers(0, 4),
    concurrency=st.integers(1, 4),
)
def test_concurrent_crawl_visits_exactly_what_sequential_bfs_does(links_by_page, max_depth, concurrency):
    seed = next(iter(links_by_page))
    source = FakeSource(seed_pages=(seed,), max_concurrent_requests_per_host=concurrency)
    result = asyncio.run(crawl_fake_site(FakeSite(links_by_page), source, max_depth=max_depth))
    assert result.visited_urls == {fake_url(page) for page in sequential_bfs(links_by_page, seed, max_depth)}


async def test_fetched_pages_carry_the_crawl_run_id():
    store = InMemoryPageStore()
    result = await crawl_fake_site(FakeSite(EXAMPLE_SITE), page_store=store)
    assert {page.crawl_run_id async for page in store.iter_pages("fake")} == {result.run.id}


async def test_the_run_is_saved_when_it_starts_and_when_it_ends():
    store = InMemoryPageStore()
    started_runs = []
    original_save_run = store.save_run

    async def remember_save(run):
        started_runs.append(run.finished_at)
        await original_save_run(run)

    store.save_run = remember_save
    await crawl_fake_site(FakeSite(EXAMPLE_SITE), page_store=store)
    assert started_runs[0] is None
    assert started_runs[-1] is not None


async def test_a_cancelled_crawl_records_why_it_stopped():
    store = InMemoryPageStore()
    site = FakeSite({"A": []})
    site.response_delay_seconds = 5
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        crawl_task = asyncio.create_task(crawl(FakeSource(), http_client, page_store=store))
        await asyncio.sleep(0.05)
        crawl_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await crawl_task
    [run] = store.saved_runs
    assert run.error is not None and run.error.startswith("CancelledError")
    assert run.finished_at is not None


async def test_a_forbidden_page_stops_the_whole_crawl():
    site = FakeSite({"A": ["B", "C", "D"], "B": [], "C": [], "D": []})
    site.script("B", lambda: httpx.Response(403))
    result = await crawl_fake_site(site)
    assert result.run.error is not None and "answered 403" in result.run.error
    assert site.fetched_page_names() == {"A", "B"}


async def test_failures_in_a_row_stop_the_crawl():
    hub = {"A": [str(i) for i in range(10)]}
    site = FakeSite(hub)
    result = await crawl_fake_site(site, FakeSource(max_retries=0, max_consecutive_failures=3))
    assert result.run.error is not None and "3 failures in a row" in result.run.error
    assert len(site.fetched_page_names()) == 4


async def test_a_success_resets_the_failure_count():
    site = FakeSite({"A": ["x1", "x2", "B", "x3", "x4"], "B": []})
    result = await crawl_fake_site(site, FakeSource(max_retries=0, max_consecutive_failures=3))
    assert result.run.error is None
    assert result.run.pages_failed == 4
