import asyncio
import json
from collections import Counter, deque
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx

from soundshark.models import CrawlPolicy, CrawlResult, CrawlRun, Event, Page, ParsedPage, StoredPageVersion
from soundshark.services import crawl
from soundshark.sources import DemoSource

FAKE_SITE_URL = "https://site.test"


def fake_url(page_name: str) -> str:
    return f"{FAKE_SITE_URL}/{page_name}"


def fast_policy(**overrides) -> CrawlPolicy:
    settings = {"seconds_between_requests_per_host": 0, "retry_backoff_seconds": 0.001} | overrides
    return CrawlPolicy(**settings)


class FakeSource:
    name = "fake"

    def __init__(self, seed_pages=("A",), *, refetch_after: timedelta | None = None, **policy) -> None:
        self.seed_urls = tuple(fake_url(page) for page in seed_pages)
        self.crawl_policy = fast_policy(**policy)
        self._refetch_after = refetch_after

    def parse(self, page: Page) -> ParsedPage:
        fake_page = json.loads(page.text)
        if fake_page.get("unparseable"):
            raise RuntimeError("this fake page can't be parsed")
        event = Event(
            source=self.name,
            source_id=page.url,
            starts_at=datetime(2026, 1, 1, tzinfo=UTC),
            venue="Fake Venue",
            city="Fake City",
        )
        return ParsedPage(events=[event], links_to_follow=[fake_url(n) for n in fake_page.get("links", [])])

    def refetch_after(self, url: str) -> timedelta | None:
        return self._refetch_after


class FakeSite:
    def __init__(
        self, links_by_page: dict[str, list[str]], robots_txt: str | int | Callable[[], httpx.Response] = 404
    ) -> None:
        self.links_by_page = links_by_page
        self.robots_txt = robots_txt
        self.requests_per_path: Counter[str] = Counter()
        self.requested_urls: list[str] = []
        self.page_request_times: list[float] = []
        self.concurrent_requests = 0
        self.peak_concurrent_requests = 0
        self.scripted_responses: dict[str, deque[Callable[[], httpx.Response]]] = {}
        self.response_delay_seconds = 0.0

    def script(self, page_name: str, *responses: Callable[[], httpx.Response]) -> None:
        self.scripted_responses[f"/{page_name}"] = deque(responses)

    def fetched_page_names(self) -> set[str]:
        return {path.lstrip("/") for path in self.requests_per_path if path != "/robots.txt"}

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests_per_path[path] += 1
        self.requested_urls.append(str(request.url))
        if path == "/robots.txt":
            return self._robots_response()
        self.page_request_times.append(asyncio.get_running_loop().time())
        self.concurrent_requests += 1
        self.peak_concurrent_requests = max(self.peak_concurrent_requests, self.concurrent_requests)
        try:
            await asyncio.sleep(self.response_delay_seconds)
            if scripted := self.scripted_responses.get(path):
                return scripted.popleft()()
            page_name = path.lstrip("/")
            if page_name not in self.links_by_page:
                return httpx.Response(404)
            return httpx.Response(200, json={"links": self.links_by_page[page_name]})
        finally:
            self.concurrent_requests -= 1

    def _robots_response(self) -> httpx.Response:
        if isinstance(self.robots_txt, int):
            return httpx.Response(self.robots_txt)
        if callable(self.robots_txt):
            return self.robots_txt()
        return httpx.Response(200, text=self.robots_txt)


class InMemoryPageStore:
    def __init__(self) -> None:
        self.versions: dict[tuple[str, str], list[Page]] = {}
        self.runs_by_id: dict[str, CrawlRun] = {}

    @property
    def saved_runs(self) -> list[CrawlRun]:
        return list(self.runs_by_id.values())

    async def load_page(self, source_name: str, url: str) -> Page | None:
        versions = self.versions.get((source_name, url))
        return versions[-1] if versions else None

    async def save_page(self, source_name: str, page: Page) -> None:
        versions = self.versions.setdefault((source_name, page.url), [])
        if versions and versions[-1].content_sha256 == page.content_sha256:
            versions[-1] = page
        else:
            versions.append(page)

    async def iter_pages(self, source_name: str) -> AsyncIterator[Page]:
        for (stored_source, _), versions in self.versions.items():
            if stored_source == source_name:
                yield versions[-1]

    async def iter_page_versions(self, source_name: str) -> AsyncIterator[StoredPageVersion]:
        for (stored_source, url), versions in self.versions.items():
            if stored_source != source_name:
                continue
            for position, page in enumerate(versions):
                yield StoredPageVersion(
                    page=page,
                    storage_path=f"memory/{source_name}/{url}/{position}",
                    is_latest=position == len(versions) - 1,
                )

    async def save_run(self, run: CrawlRun) -> None:
        self.runs_by_id[run.id] = replace(run)

    async def iter_runs(self, source_name: str) -> AsyncIterator[CrawlRun]:
        for run in self.runs_by_id.values():
            if run.source_name == source_name:
                yield run


async def crawl_fake_site(site: FakeSite, source: FakeSource | None = None, **crawl_options) -> CrawlResult:
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        async with asyncio.timeout(10):
            return await crawl(source or FakeSource(), http_client, **crawl_options)


async def crawl_demo_into_memory() -> InMemoryPageStore:
    source = DemoSource(seconds_between_requests=0)
    store = InMemoryPageStore()
    async with httpx.AsyncClient(transport=source.http_transport) as http_client:
        await crawl(source, http_client, page_store=store)
    return store
