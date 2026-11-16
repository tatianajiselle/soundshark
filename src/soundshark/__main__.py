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
from soundshark.services.credits import CreditSummary, build_credits
from soundshark.services.graph_job import GraphSummary, rebuild_artist_graph
from soundshark.services.ingest import IngestSummary, ingest_stored_pages
from soundshark.services.related_lookup import ArtistNotFound, RelatedArtists, related_artists
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


async def identify_artists(rebuild: bool) -> None:
    engine = create_database_engine(database_url_from_env())
    try:
        print_credit_summary(await build_credits(engine, rebuild=rebuild))
    finally:
        await engine.dispose()


async def rebuild_graph() -> None:
    engine = create_database_engine(database_url_from_env())
    try:
        print_graph_summary(await rebuild_artist_graph(engine))
    finally:
        await engine.dispose()


async def show_related(name: str, limit: int) -> int:
    engine = create_database_engine(database_url_from_env())
    try:
        answer = await related_artists(engine, name, limit=limit)
    finally:
        await engine.dispose()
    if isinstance(answer, ArtistNotFound):
        print(f"No artist called {answer.query!r}.")
        if answer.did_you_mean:
            print("Did you mean: " + ", ".join(answer.did_you_mean))
        return 1
    print_related(answer)
    return 0


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
        f"{source_name:12} {summary.page_versions_read} page versions  {summary.pages_parsed} parsed  "
        f"{summary.events_written} events  {summary.events_with_new_lineups} with new lineups  "
        f"{summary.lineup_slots_written} lineup slots written  {summary.pages_unparseable} unparseable"
    )


def print_credit_summary(summary: CreditSummary) -> None:
    print(
        f"{summary.lineup_slots_read} lineup slots credited  {summary.credits_written} credits  "
        f"{summary.artists_created} new artists  "
        f"{summary.automatic_aliases_removed} automatic aliases removed  "
        f"{summary.artists_removed} artists removed"
    )


def print_graph_summary(summary: GraphSummary) -> None:
    print(
        f"{summary.credits_read} credits  {summary.artists_in_graph} artists  {summary.edges_written} edges  "
        f"{summary.related_rows_written} related rows  scored in {summary.scoring_seconds}s"
    )


def print_related(answer: RelatedArtists) -> None:
    artist = answer.artist
    span = ""
    if artist.first_night and artist.last_night:
        span = f", {artist.first_night:%Y-%m} to {artist.last_night:%Y-%m}"
    computed = f"  (graph computed {answer.computed_at:%Y-%m-%d %H:%M} UTC)" if answer.computed_at else ""
    print(f"{artist.name}: {artist.nights} nights{span}{computed}\n")
    if not answer.related:
        print("No related artists yet. Run `soundshark graph` first.")
        return
    name_width = max(len(r.name) for r in answer.related)
    print(f" #  {'artist':<{name_width}}  nights together  same room  b2b  last together")
    for r in answer.related:
        if r.nights_together:
            last = f"{r.last_together:%Y-%m}" if r.last_together else ""
            together = f"{r.nights_together:>15}  {r.same_room:>9}  {r.b2b:>3}  {last}"
        else:
            together = f"{'':>15}  never on the same bill; connected through others"
        print(f"{r.rank:>2}  {r.name:<{name_width}}  {together}")


def build_parser() -> argparse.ArgumentParser:
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
    identify_command = commands.add_parser("identify", parents=[shared], help="match lineup slots to artists")
    identify_command.add_argument(
        "--rebuild", action="store_true", help="forget automatic matches first; manual aliases are kept"
    )
    commands.add_parser("graph", parents=[shared], help="rebuild artist edges and related artists")
    related_command = commands.add_parser("related", parents=[shared], help="who is closest to an artist")
    related_command.add_argument("name", help="the artist, spelled any way")
    related_command.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(find_dotenv(usecwd=True))
    configure_logging(verbose=args.verbose, json_output=args.log_json)
    if args.command == "crawl":
        asyncio.run(crawl_all_sources(args.store, args.max_pages, args.max_depth))
    elif args.command == "ingest":
        asyncio.run(ingest_all_sources(args.store))
    elif args.command == "identify":
        asyncio.run(identify_artists(args.rebuild))
    elif args.command == "graph":
        asyncio.run(rebuild_graph())
    else:
        return asyncio.run(show_related(args.name, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
