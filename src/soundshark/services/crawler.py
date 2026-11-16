import asyncio
import time
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import structlog
from structlog.typing import FilteringBoundLogger

from soundshark.clients import PoliteHttpClient, RobotsRules
from soundshark.interfaces import PageStore, Source
from soundshark.models import CrawlResult, CrawlRun, Event, Page
from soundshark.utils import is_web_url, without_fragment

log: FilteringBoundLogger = structlog.get_logger()


async def crawl(
    source: Source,
    http_client: httpx.AsyncClient,
    *,
    page_store: PageStore | None = None,
    max_depth: int | None = None,
    max_pages: int = 1000,
) -> CrawlResult:
    run = CrawlRun(source_name=source.name)
    run_log = log.bind(source=source.name, run_id=run.id)
    job = _CrawlJob(source, http_client, page_store, max_depth, max_pages, run, run_log)

    run_log.info("crawl.started", seed_urls=list(source.seed_urls), max_pages=max_pages, max_depth=max_depth)
    started = time.perf_counter()
    if page_store is not None:
        await page_store.save_run(run)
    try:
        for url in source.seed_urls:
            job.enqueue_if_new(url, depth=0)
        await job.run_workers_until_queue_is_empty()
    except BaseException as error:
        run.error = f"{type(error).__name__}: {error}"
        run_log.error("crawl.crashed", error=run.error)
        raise
    finally:
        run.finished_at = datetime.now(UTC)
        if page_store is not None:
            await page_store.save_run(run)

    run_log.info(
        "crawl.finished",
        pages_fetched=run.pages_fetched,
        pages_from_store=run.pages_from_store,
        pages_failed=run.pages_failed,
        pages_blocked_by_robots=run.pages_blocked_by_robots,
        events_found=run.events_found,
        duration_seconds=round(time.perf_counter() - started, 2),
    )
    return CrawlResult(events=job.events, visited_urls=job.visited_urls, run=run)


class _CrawlJob:
    def __init__(
        self,
        source: Source,
        http_client: httpx.AsyncClient,
        page_store: PageStore | None,
        max_depth: int | None,
        max_pages: int,
        run: CrawlRun,
        log: FilteringBoundLogger,
    ) -> None:
        self.source = source
        self.http = PoliteHttpClient(http_client, source.crawl_policy, log)
        self.robots = RobotsRules(self.http, log)
        self.page_store = page_store
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.run = run
        self.log = log
        self.queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self.visited_urls: set[str] = set()
        self.events: list[Event] = []

    def enqueue_if_new(self, url: str, depth: int) -> None:
        url = without_fragment(url)
        if url in self.visited_urls or not is_web_url(url):
            return
        if len(self.visited_urls) >= self.max_pages:
            return
        self.visited_urls.add(url)
        self.queue.put_nowait((url, depth))

    async def run_workers_until_queue_is_empty(self) -> None:
        worker_count = max(1, self.source.crawl_policy.max_concurrent_requests_per_host)
        async with asyncio.TaskGroup() as task_group:
            workers = [task_group.create_task(self._work_through_queue()) for _ in range(worker_count)]
            await self.queue.join()
            for worker in workers:
                worker.cancel()

    async def _work_through_queue(self) -> None:
        while True:
            url, depth = await self.queue.get()
            try:
                await self._process(url, depth)
            except Exception:
                self.run.pages_failed += 1
                self.log.exception("page.unexpected_error", url=url, depth=depth)
            finally:
                self.queue.task_done()

    async def _process(self, url: str, depth: int) -> None:
        page = await self._fresh_stored_copy(url)
        if page is not None:
            self.run.pages_from_store += 1
            self.log.debug("page.from_store", url=url, depth=depth, fetched_at=page.fetched_at.isoformat())
        else:
            page = await self._fetch_and_store(url, depth)
            if page is None:
                return

        try:
            parsed = self.source.parse(page)
        except Exception:
            self.run.pages_failed += 1
            self.log.exception("page.parse_failed", url=url, depth=depth)
            return

        self.events.extend(parsed.events)
        self.run.events_found += len(parsed.events)
        self.log.debug(
            "page.parsed", url=url, depth=depth, events=len(parsed.events), links=len(parsed.links_to_follow)
        )
        if self.max_depth is None or depth < self.max_depth:
            for link in parsed.links_to_follow:
                self.enqueue_if_new(link, depth + 1)

    async def _fetch_and_store(self, url: str, depth: int) -> Page | None:
        if not await self.robots.is_allowed(url):
            self.run.pages_blocked_by_robots += 1
            self.log.info("page.blocked_by_robots", url=url, depth=depth)
            return None
        fetched = await self.http.fetch_page(url)
        if fetched is None:
            self.run.pages_failed += 1
            return None
        page = replace(fetched, crawl_run_id=self.run.id)
        self.run.pages_fetched += 1
        if self.page_store is not None:
            await self.page_store.save_page(self.source.name, page)
        return page

    async def _fresh_stored_copy(self, url: str) -> Page | None:
        if self.page_store is None:
            return None
        stored = await self.page_store.load_page(self.source.name, url)
        if stored is None:
            return None
        max_age = self.source.refetch_after(url)
        if max_age is None or datetime.now(UTC) - stored.fetched_at < max_age:
            return stored
        return None
