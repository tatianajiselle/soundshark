import argparse
import asyncio
import logging
import time

import httpx
from dotenv import load_dotenv

from soundshark.crawler import CrawlResult, crawl
from soundshark.sources.base import Source
from soundshark.sources.loader import load_sources


async def run(source: Source, max_pages: int, max_depth: int | None) -> CrawlResult:
    transport = getattr(source, "transport", None)
    async with httpx.AsyncClient(transport=transport) as client:
        return await crawl(source, client, max_pages=max_pages, max_depth=max_depth)


async def main(max_pages: int, max_depth: int | None) -> None:
    load_dotenv()
    sources = load_sources()
    start = time.perf_counter()
    async with asyncio.TaskGroup() as tg:
        tasks = {s.name: tg.create_task(run(s, max_pages, max_depth)) for s in sources}
    for name, task in tasks.items():
        result = task.result()
        artists = {a for e in result.events for a in e.artists}
        r = result.run
        print(
            f"{name:12} {len(result.events):5} events  {len(artists):5} artists  "
            f"{r.fetched} fetched  {r.from_store} stored  {r.failed} failed  {r.blocked} blocked"
        )
    print(f"done in {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="soundshark")
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    asyncio.run(main(args.max_pages, args.max_depth))
