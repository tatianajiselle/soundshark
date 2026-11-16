import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urldefrag, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from soundshark.models import Event
from soundshark.pages import Page
from soundshark.sources.base import Politeness, Source
from soundshark.store.base import CrawlRun, RawStore

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(slots=True)
class CrawlResult:
    events: list[Event]
    visited: set[str]
    run: CrawlRun


@dataclass(slots=True)
class _Host:
    slots: asyncio.Semaphore
    interval: float
    next_start: float = 0.0

    async def turn(self) -> None:
        now = asyncio.get_running_loop().time()
        start = max(now, self.next_start)
        self.next_start = start + self.interval
        if start > now:
            await asyncio.sleep(start - now)

    def pause_until(self, when: float) -> None:
        self.next_start = max(self.next_start, when)


@dataclass(slots=True)
class _Crawl:
    source: Source
    client: httpx.AsyncClient
    store: RawStore | None
    max_depth: int | None
    max_pages: int
    run: CrawlRun
    queue: asyncio.Queue[tuple[str, int]] = field(default_factory=asyncio.Queue)
    visited: set[str] = field(default_factory=set)
    events: list[Event] = field(default_factory=list)
    hosts: dict[str, _Host] = field(default_factory=dict)
    robots: dict[str, asyncio.Task[RobotFileParser]] = field(default_factory=dict)

    @property
    def polite(self) -> Politeness:
        return self.source.politeness

    def schedule(self, url: str, depth: int) -> None:
        url = urldefrag(url).url
        if url in self.visited or len(self.visited) >= self.max_pages:
            return
        if urlsplit(url).scheme not in ("http", "https"):
            return
        self.visited.add(url)
        self.queue.put_nowait((url, depth))

    async def worker(self) -> None:
        while True:
            url, depth = await self.queue.get()
            try:
                await self.process(url, depth)
            except Exception:
                self.run.failed += 1
                log.exception("%s: giving up on %s", self.source.name, url)
            finally:
                self.queue.task_done()

    async def process(self, url: str, depth: int) -> None:
        page = await self.stored(url)
        if page is not None:
            self.run.from_store += 1
        else:
            if not await self.allowed(url):
                self.run.blocked += 1
                log.info("%s: robots.txt disallows %s", self.source.name, url)
                return
            page = await self.fetch(url)
            if page is None:
                self.run.failed += 1
                return
            self.run.fetched += 1
            if self.store is not None:
                await self.store.put(self.source.name, page)
        parsed = self.source.parse(page)
        self.events.extend(parsed.events)
        self.run.events += len(parsed.events)
        if self.max_depth is None or depth < self.max_depth:
            for link in parsed.links:
                self.schedule(link, depth + 1)

    async def stored(self, url: str) -> Page | None:
        if self.store is None:
            return None
        page = await self.store.get(self.source.name, url)
        if page is None:
            return None
        max_age = self.source.refresh_after(url)
        if max_age is None or datetime.now(UTC) - page.fetched_at < max_age:
            return page
        return None

    def host(self, url: str) -> _Host:
        key = _origin(url)
        if key not in self.hosts:
            self.hosts[key] = _Host(asyncio.Semaphore(self.polite.max_in_flight), self.polite.min_interval)
        return self.hosts[key]

    async def allowed(self, url: str) -> bool:
        key = _origin(url)
        if key not in self.robots:
            self.robots[key] = asyncio.create_task(self.load_robots(key))
        robots = await self.robots[key]
        return robots.can_fetch(self.polite.user_agent, url)

    async def load_robots(self, origin: str) -> RobotFileParser:
        robots = RobotFileParser(f"{origin}/robots.txt")
        response = await self.request(f"{origin}/robots.txt")
        if response is None or response.status_code >= 500:
            robots.parse(["User-agent: *", "Disallow: /"])
        elif response.status_code >= 400:
            robots.parse([])
        else:
            robots.parse(response.text.splitlines())
            delay = robots.crawl_delay(self.polite.user_agent)
            if delay is not None:
                host = self.host(origin)
                host.interval = max(host.interval, float(delay))
        return robots

    async def fetch(self, url: str) -> Page | None:
        response = await self.request(url)
        if response is None:
            return None
        if not response.is_success:
            log.warning("%s: %s returned %s", self.source.name, url, response.status_code)
            return None
        return Page(
            url=url,
            status=response.status_code,
            body=response.content,
            fetched_at=datetime.now(UTC),
            content_type=response.headers.get("content-type"),
            encoding=response.encoding or "utf-8",
        )

    async def request(self, url: str) -> httpx.Response | None:
        host = self.host(url)
        headers = {"User-Agent": self.polite.user_agent}
        for attempt in range(self.polite.max_retries + 1):
            last = attempt == self.polite.max_retries
            try:
                async with host.slots:
                    await host.turn()
                    response = await self.client.get(
                        url, headers=headers, timeout=self.polite.timeout, follow_redirects=True
                    )
            except httpx.TransportError as error:
                log.warning("%s: %s failed (%s), attempt %d", self.source.name, url, error, attempt + 1)
                if last:
                    return None
                await asyncio.sleep(self.backoff(attempt))
                continue
            if response.status_code not in RETRY_STATUSES or last:
                return response
            wait = _retry_after(response) or self.backoff(attempt)
            if wait > self.polite.max_retry_after:
                log.warning("%s: %s asks to wait %.0fs, skipping", self.source.name, url, wait)
                return response
            host.pause_until(asyncio.get_running_loop().time() + wait)
        return None

    def backoff(self, attempt: int) -> float:
        return self.polite.backoff * 2**attempt * random.uniform(0.5, 1.0)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    if value.strip().isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


async def crawl(
    source: Source,
    client: httpx.AsyncClient,
    *,
    store: RawStore | None = None,
    max_depth: int | None = None,
    max_pages: int = 1000,
) -> CrawlResult:
    state = _Crawl(source, client, store, max_depth, max_pages, CrawlRun(source.name))
    for seed in source.seeds:
        state.schedule(seed, 0)
    workers = max(1, source.politeness.max_in_flight)
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(state.worker()) for _ in range(workers)]
        await state.queue.join()
        for task in tasks:
            task.cancel()
    state.run.finished_at = datetime.now(UTC)
    if store is not None:
        await store.save_run(state.run)
    return CrawlResult(state.events, state.visited, state.run)
