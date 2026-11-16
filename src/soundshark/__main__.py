import argparse
import asyncio
import time
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv

from soundshark.db import create_database_engine, database_url_from_env
from soundshark.interfaces import PageStore, Source
from soundshark.models import CrawlResult
from soundshark.services import crawl
from soundshark.services.ingest import IngestSummary, ingest_stored_pages
from soundshark.sources import load_configured_sources
from soundshark.stores import FilePageStore
from soundshark.utils import configure_logging

DEFAULT_STORE_DIR = Path("data")


async def crawl_one_source(
    source: Source, page_store: PageStore, max_pages: int, max_depth: int | None
) -> CrawlResult:
    offline_transport = getattr(source, "http_transport", None)
    async with httpx.AsyncClient(transport=offline_transport) as http_client:
        return await crawl(
            source, http_client, page_store=page_store, max_pages=max_pages, max_depth=max_depth
        )


async def crawl_all_sources(store_dir: Path, max_pages: int, max_depth: int | None) -> None:
    sources = load_configured_sources()
    page_store = FilePageStore(store_dir)
    started = time.perf_counter()
    async with asyncio.TaskGroup() as task_group:
        crawls = {
            s.name: task_group.create_task(crawl_one_source(s, page_store, max_pages, max_depth))
            for s in sources
        }
    for source_name, finished_crawl in crawls.items():
        print_crawl_summary(source_name, finished_crawl.result())
    print(f"done in {time.perf_counter() - started:.2f}s")


async def ingest_all_sources(store_dir: Path) -> None:
    engine = create_database_engine(database_url_from_env())
    page_store = FilePageStore(store_dir)
    started = time.perf_counter()
    try:
        for source in load_configured_sources():
            print_ingest_summary(source.name, await ingest_stored_pages(engine, source, page_store))
    finally:
        await engine.dispose()
    print(f"done in {time.perf_counter() - started:.2f}s")


def print_crawl_summary(source_name: str, result: CrawlResult) -> None:
    artists = {artist for event in result.events for artist in event.artists}
    run = result.run
    print(
        f"{source_name:12} {len(result.events):5} events  {len(artists):5} artists  "
        f"{run.pages_fetched} fetched  {run.pages_from_store} from store  "
        f"{run.pages_failed} failed  {run.pages_blocked_by_robots} blocked by robots.txt"
    )


def print_ingest_summary(source_name: str, summary: IngestSummary) -> None:
    print(
        f"{source_name:12} {summary.pages_read} pages read  {summary.events_written} events  "
        f"{summary.lineup_slots_written} lineup slots  {summary.artists_created} new artists  "
        f"{summary.pages_unparseable} unparseable pages"
    )


def parse_args() -> argparse.Namespace:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--store", type=Path, default=DEFAULT_STORE_DIR, help="where fetched pages are kept")
    shared.add_argument("-v", "--verbose", action="store_true", help="also log every request and page")
    shared.add_argument("--log-json", action="store_true", help="one JSON object per log line")

    parser = argparse.ArgumentParser(prog="soundshark")
    commands = parser.add_subparsers(dest="command", required=True)
    crawl_command = commands.add_parser("crawl", parents=[shared], help="fetch pages into the store")
    crawl_command.add_argument("--max-pages", type=int, default=1000)
    crawl_command.add_argument("--max-depth", type=int, default=None)
    commands.add_parser("ingest", parents=[shared], help="parse stored pages into Postgres")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    load_dotenv(find_dotenv(usecwd=True))
    configure_logging(verbose=args.verbose, json_output=args.log_json)
    if args.command == "crawl":
        asyncio.run(crawl_all_sources(args.store, args.max_pages, args.max_depth))
    else:
        asyncio.run(ingest_all_sources(args.store))
