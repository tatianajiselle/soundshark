import asyncio
import json
from collections import Counter, deque
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from soundshark.crawler import crawl
from soundshark.models import Event
from soundshark.pages import Page, Parsed
from soundshark.sources.base import Politeness
from soundshark.store.base import CrawlRun, RawStore

BASE = "https://site.test"


def url(name: str) -> str:
    return f"{BASE}/{name}"


class FakeSource:
    name = "fake"

    def __init__(self, seeds=("A",), *, refresh: timedelta | None = None, **polite) -> None:
        self.seeds = tuple(url(s) for s in seeds)
        self.politeness = Politeness(**{"min_interval": 0, "backoff": 0.001, **polite})
        self.refresh = refresh

    def parse(self, page: Page) -> Parsed:
        data = json.loads(page.text)
        if data.get("explode"):
            raise RuntimeError("bad page")
        events = [
            Event(
                source=self.name,
                source_id=page.url,
                starts_at=datetime(2026, 1, 1, tzinfo=UTC),
                venue="V",
                city="C",
            )
        ]
        return Parsed(events=events, links=[url(n) for n in data.get("links", [])])

    def refresh_after(self, url: str) -> timedelta | None:
        return self.refresh


class Site:
    """A fake website: graph of page name -> linked names, plus per-path response overrides."""

    def __init__(self, graph: dict[str, list[str]], robots: str | int = 404) -> None:
        self.graph = graph
        self.robots = robots
        self.hits: Counter[str] = Counter()
        self.times: list[float] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.overrides: dict[str, deque[Callable[[], httpx.Response]]] = {}
        self.delay = 0.0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.hits[path] += 1
        if path == "/robots.txt":
            if isinstance(self.robots, int):
                return httpx.Response(self.robots)
            return httpx.Response(200, text=self.robots)
        self.times.append(asyncio.get_running_loop().time())
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if queue := self.overrides.get(path):
                return queue.popleft()()
            name = path.lstrip("/")
            if name not in self.graph:
                return httpx.Response(404)
            return httpx.Response(200, json={"links": self.graph[name]})
        finally:
            self.in_flight -= 1

    def fetched(self) -> set[str]:
        return {p.lstrip("/") for p in self.hits if p != "/robots.txt"}


async def run(site, source=None, **kwargs):
    source = source or FakeSource()
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as client:
        async with asyncio.timeout(10):
            return await crawl(source, client, **kwargs)


EXAMPLE = {"A": ["B", "C"], "B": ["C", "D"], "C": ["A"], "D": ["E"], "E": []}


@pytest.mark.parametrize(("depth", "expected"), [(0, "A"), (1, "ABC"), (2, "ABCD"), (None, "ABCDE")])
async def test_bfs_depth_limits(depth, expected):
    site = Site(EXAMPLE)
    result = await run(site, max_depth=depth)
    assert result.visited == {url(n) for n in expected}
    assert site.fetched() == set(expected)


async def test_never_fetches_a_url_twice():
    graph = {n: [m for m in "ABCDEF" if m != n] for n in "ABCDEF"}
    site = Site(graph)
    await run(site, FakeSource(max_in_flight=4))
    assert all(count == 1 for count in site.hits.values())


async def test_max_pages_caps_fetches():
    graph = {str(i): [str(i * 3 + k) for k in (1, 2, 3)] for i in range(50)}
    site = Site(graph)
    result = await run(site, FakeSource(seeds=("0",), max_in_flight=3), max_pages=5)
    assert len(result.visited) == 5
    assert len(site.fetched()) == 5


async def test_events_and_run_counts():
    result = await run(Site(EXAMPLE))
    assert len(result.events) == 5
    assert result.run.fetched == 5
    assert result.run.events == 5
    assert result.run.finished_at is not None


async def test_dead_host_returns_quickly():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        async with asyncio.timeout(5):
            result = await crawl(FakeSource(max_retries=2), client)
    assert result.events == []
    assert result.visited == {url("A")}
    assert result.run.fetched == 0


async def test_failed_and_broken_pages_are_skipped():
    site = Site({"A": ["B", "C", "missing"], "B": [], "C": []})
    site.overrides["/B"] = deque([lambda: httpx.Response(200, json={"explode": True})])
    result = await run(site)
    assert result.run.fetched == 3
    assert result.run.failed == 2
    assert {e.source_id for e in result.events} == {url("A"), url("C")}


async def test_respects_max_in_flight():
    graph = {"A": [str(i) for i in range(12)], **{str(i): [] for i in range(12)}}
    site = Site(graph)
    site.delay = 0.02
    await run(site, FakeSource(max_in_flight=3))
    assert site.max_in_flight == 3


async def test_spaces_requests_per_host():
    site = Site({"A": ["B", "C", "D"], "B": [], "C": [], "D": []})
    await run(site, FakeSource(min_interval=0.05, max_in_flight=4))
    gaps = [b - a for a, b in zip(site.times, site.times[1:], strict=False)]
    assert len(gaps) == 3
    assert min(gaps) >= 0.045


async def test_robots_disallow_is_obeyed():
    site = Site(EXAMPLE, robots="User-agent: *\nDisallow: /C\n")
    result = await run(site)
    assert "C" not in site.fetched()
    assert result.run.blocked == 1


async def test_robots_rules_for_our_user_agent():
    site = Site(EXAMPLE, robots="User-agent: soundshark\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    result = await run(site)
    assert site.fetched() == set()
    assert result.run.blocked == 1


async def test_robots_server_error_means_disallow_all():
    site = Site(EXAMPLE, robots=503)
    result = await run(site, FakeSource(max_retries=0))
    assert site.fetched() == set()
    assert result.run.blocked == 1


async def test_robots_crawl_delay_slows_us_down():
    site = Site({"A": ["B"], "B": []}, robots="User-agent: *\nCrawl-delay: 1\n")
    await run(site)
    assert site.times[1] - site.times[0] >= 0.95


async def test_robots_fetched_once_per_host():
    site = Site({n: list("ABCDEF") for n in "ABCDEF"}, robots="User-agent: *\nAllow: /\n")
    await run(site, FakeSource(max_in_flight=4))
    assert site.hits["/robots.txt"] == 1


async def test_retries_server_errors_then_succeeds():
    site = Site({"A": []})
    site.overrides["/A"] = deque([lambda: httpx.Response(503), lambda: httpx.Response(500)])
    result = await run(site)
    assert site.hits["/A"] == 3
    assert result.run.fetched == 1


async def test_gives_up_after_max_retries():
    site = Site({"A": []})
    site.overrides["/A"] = deque([lambda: httpx.Response(503)] * 10)
    result = await run(site, FakeSource(max_retries=2))
    assert site.hits["/A"] == 3
    assert result.run.failed == 1


async def test_honours_retry_after():
    site = Site({"A": []})
    site.overrides["/A"] = deque([lambda: httpx.Response(429, headers={"Retry-After": "1"})])
    await run(site)
    assert site.times[1] - site.times[0] >= 0.95


async def test_skips_absurd_retry_after():
    site = Site({"A": []})
    site.overrides["/A"] = deque([lambda: httpx.Response(429, headers={"Retry-After": "86400"})])
    result = await run(site)
    assert site.hits["/A"] == 1
    assert result.run.failed == 1


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], Page] = {}
        self.runs: list[CrawlRun] = []

    async def get(self, source: str, url: str) -> Page | None:
        return self.data.get((source, url))

    async def put(self, source: str, page: Page) -> None:
        self.data[(source, page.url)] = page

    async def pages(self, source: str) -> AsyncIterator[Page]:
        for (s, _), page in self.data.items():
            if s == source:
                yield page

    async def save_run(self, run: CrawlRun) -> None:
        self.runs.append(run)


async def test_store_serves_fresh_pages_without_refetching():
    store = MemoryStore()
    assert isinstance(store, RawStore)
    first = await run(Site(EXAMPLE), store=store)
    site = Site(EXAMPLE)
    second = await run(site, store=store)
    assert first.run.fetched == 5
    assert second.run.from_store == 5
    assert site.fetched() == set()
    assert len(second.events) == 5
    assert len(store.runs) == 2


async def test_store_refetches_stale_pages():
    store = MemoryStore()
    await run(Site(EXAMPLE), store=store)
    site = Site(EXAMPLE)
    second = await run(site, FakeSource(refresh=timedelta(0)), store=store)
    assert second.run.fetched == 5


def reference_bfs(graph: dict[str, list[str]], seed: str, max_depth: int | None) -> set[str]:
    seen, frontier = {seed}, deque([(seed, 0)])
    while frontier:
        node, depth = frontier.popleft()
        if node not in graph or (max_depth is not None and depth >= max_depth):
            continue
        for link in graph[node]:
            if link not in seen:
                seen.add(link)
                frontier.append((link, depth + 1))
    return seen


names = st.sampled_from([str(i) for i in range(12)])


@settings(max_examples=60, deadline=None)
@given(
    graph=st.dictionaries(names, st.lists(names, max_size=5), min_size=1),
    max_depth=st.none() | st.integers(0, 4),
    workers=st.integers(1, 4),
)
def test_matches_sequential_bfs(graph, max_depth, workers):
    seed = next(iter(graph))
    result = asyncio.run(
        run(Site(graph), FakeSource(seeds=(seed,), max_in_flight=workers), max_depth=max_depth)
    )
    assert result.visited == {url(n) for n in reference_bfs(graph, seed, max_depth)}
