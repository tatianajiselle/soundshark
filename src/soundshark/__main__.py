import argparse
import asyncio
import time

import httpx
from dotenv import load_dotenv

from soundshark.interfaces import Source
from soundshark.models import CrawlResult
from soundshark.services import crawl
from soundshark.sources import load_configured_sources
from soundshark.utils import configure_logging


async def crawl_one_source(source: Source, max_pages: int, max_depth: int | None) -> CrawlResult:
    offline_transport = getattr(source, "http_transport", None)
    async with httpx.AsyncClient(transport=offline_transport) as http_client:
        return await crawl(source, http_client, max_pages=max_pages, max_depth=max_depth)


async def crawl_all_sources(max_pages: int, max_depth: int | None) -> None:
    sources = load_configured_sources()
    started = time.perf_counter()
    async with asyncio.TaskGroup() as task_group:
        crawls = {s.name: task_group.create_task(crawl_one_source(s, max_pages, max_depth)) for s in sources}
    for source_name, finished_crawl in crawls.items():
        print_summary(source_name, finished_crawl.result())
    print(f"done in {time.perf_counter() - started:.2f}s")


def print_summary(source_name: str, result: CrawlResult) -> None:
    artists = {artist for event in result.events for artist in event.artists}
    run = result.run
    print(
        f"{source_name:12} {len(result.events):5} events  {len(artists):5} artists  "
        f"{run.pages_fetched} fetched  {run.pages_from_store} from store  "
        f"{run.pages_failed} failed  {run.pages_blocked_by_robots} blocked by robots.txt"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="soundshark")
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="also log every request and page")
    parser.add_argument("--log-json", action="store_true", help="one JSON object per log line")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    load_dotenv()
    configure_logging(verbose=args.verbose, json_output=args.log_json)
    asyncio.run(crawl_all_sources(args.max_pages, args.max_depth))
