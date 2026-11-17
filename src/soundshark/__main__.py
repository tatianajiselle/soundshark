import argparse
import asyncio
import json
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv

from soundshark.db import MIGRATIONS_URL_ENV_VAR, create_database_engine, database_url_from_env
from soundshark.db.roles import (
    DEFAULT_JOBS_ROLE,
    create_or_rotate_jobs_role,
    url_for_role,
    write_env_value,
)
from soundshark.interfaces import PageStore, Source
from soundshark.models import CrawlResult
from soundshark.models.graph_scoring import GraphScoring
from soundshark.services import crawl
from soundshark.services.artist_graph import nights_per_artist, related_artist_ids
from soundshark.services.credits import CreditSummary, build_credits
from soundshark.services.graph_evaluation import Backtest, backtest
from soundshark.services.graph_job import GraphSummary, load_credits_on_bills, rebuild_artist_graph
from soundshark.services.ingest import IngestSummary, ingest_stored_pages
from soundshark.services.ranking_changes import RankingChange, ranking_changes
from soundshark.services.related_lookup import (
    ArtistNotFound,
    RelatedArtists,
    artist_names,
    related_artists,
)
from soundshark.services.scoring_variants import (
    ScoringSpecError,
    ScoringVariant,
    SettingValue,
    default_variants,
    describe_overrides,
    parse_settings,
    parse_variant,
)
from soundshark.sources import load_configured_sources
from soundshark.stores import FilePageStore
from soundshark.utils import configure_logging

DEFAULT_STORE_DIR = Path("data")
DEFAULT_CUTOFF = date(2025, 6, 1)


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


async def run_nightly_jobs(store_dir: Path, max_pages: int, max_depth: int | None) -> None:
    await crawl_all_sources(store_dir, max_pages, max_depth)
    await ingest_all_sources(store_dir)
    await identify_artists(rebuild=False)
    await rebuild_graph()


async def set_up_jobs_role(role: str, env_file: Path, env_var: str) -> None:
    owner_url = database_url_from_env(MIGRATIONS_URL_ENV_VAR)
    engine = create_database_engine(owner_url)
    try:
        password = await create_or_rotate_jobs_role(engine, role)
    finally:
        await engine.dispose()
    write_env_value(env_file, env_var, url_for_role(owner_url, role, password))
    print(f"role {role} is ready; {env_var} in {env_file} now connects as it")


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


async def evaluate_rankings(cutoff: date, variants: list[ScoringVariant], as_json: bool) -> None:
    engine = create_database_engine(database_url_from_env())
    try:
        async with engine.connect() as connection:
            credits = await load_credits_on_bills(connection)
    finally:
        await engine.dispose()
    result = await backtest(credits, datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC), variants)
    if as_json:
        print(json.dumps(backtest_as_json(result), indent=2))
    else:
        print_backtest(result)


async def show_movers(overrides: dict[str, SettingValue], top: int, min_nights: int, limit: int) -> None:
    engine = create_database_engine(database_url_from_env())
    try:
        async with engine.connect() as connection:
            credits = await load_credits_on_bills(connection)
            names = await artist_names(connection)
    finally:
        await engine.dispose()
    now = datetime.now(UTC)
    changed = ScoringVariant("changed", overrides).scoring
    before = await asyncio.to_thread(related_artist_ids, credits, GraphScoring(), now)
    after = await asyncio.to_thread(related_artist_ids, credits, changed, now)
    changes = ranking_changes(
        before, after, nights_per_artist(credits), names, top=top, min_nights=min_nights
    )
    print_movers(describe_overrides(overrides), changes, top, min_nights, limit)


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


def backtest_as_json(result: Backtest) -> dict[str, object]:
    return {
        "cutoff": result.cutoff.date().isoformat(),
        "train_nights": result.train_nights,
        "test_nights": result.test_nights,
        "future_same_room_pairs": result.future_same_room_pairs,
        "rankings": [asdict(ranking) for ranking in result.rankings],
    }


def print_backtest(result: Backtest) -> None:
    print(
        f"cutoff {result.cutoff:%Y-%m-%d}  {result.train_nights} train nights  "
        f"{result.test_nights} test nights  {result.future_same_room_pairs} future same-room pairs\n"
    )
    name_width = max(len("setting"), *(len(r.name) for r in result.rankings))
    print(f"{'setting':<{name_width}}  recall@10  new partners@50  home room@10  changes")
    for r in result.rankings:
        row = (
            f"{r.name:<{name_width}}  {r.recall_at_10:>9.3f}  {r.new_partner_recall_at_50:>15.3f}  "
            f"{r.home_room_share_at_10:>12.3f}  {describe_overrides(r.overrides)}"
        )
        print(row.rstrip())


def print_movers(changed: str, changes: list[RankingChange], top: int, min_nights: int, limit: int) -> None:
    moved = [c for c in changes if c.change > 0]
    print(
        f"{changed}: {len(moved)} of {len(changes)} artists with {min_nights}+ nights "
        f"have a different top {top}\n"
    )
    if not moved:
        return
    shown = moved[:limit]
    name_width = max(len("artist"), *(len(c.name) for c in shown))
    print(f"{'artist':<{name_width}}  nights  change  entered / left")
    for c in shown:
        print(f"{c.name:<{name_width}}  {c.nights:>6}  {c.change:>6.2f}  + {', '.join(c.entered)}")
        print(f"{'':<{name_width}}  {'':>6}  {'':>6}  - {', '.join(c.left)}")


def variant_argument(spec: str) -> ScoringVariant:
    try:
        return parse_variant(spec)
    except ScoringSpecError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--store", type=Path, default=DEFAULT_STORE_DIR, help="where fetched pages are kept")
    shared.add_argument("-v", "--verbose", action="store_true", help="also log every request and page")
    shared.add_argument("--log-json", action="store_true", help="one JSON object per log line")

    crawl_limits = argparse.ArgumentParser(add_help=False)
    crawl_limits.add_argument("--max-pages", type=int, default=1000)
    crawl_limits.add_argument("--max-depth", type=int, default=None)

    parser = argparse.ArgumentParser(prog="soundshark")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("crawl", parents=[shared, crawl_limits], help="fetch pages into the store")
    commands.add_parser("ingest", parents=[shared], help="parse stored pages into Postgres")
    identify_command = commands.add_parser("identify", parents=[shared], help="match lineup slots to artists")
    identify_command.add_argument(
        "--rebuild", action="store_true", help="forget automatic matches first; manual aliases are kept"
    )
    commands.add_parser("graph", parents=[shared], help="rebuild artist edges and related artists")
    commands.add_parser(
        "jobs",
        parents=[shared, crawl_limits],
        help="crawl, ingest, identify and graph, stopping on the first error",
    )
    role_command = commands.add_parser(
        "create-jobs-role",
        parents=[shared],
        help=f"create or rotate the limited role the jobs connect as (needs {MIGRATIONS_URL_ENV_VAR})",
    )
    role_command.add_argument("--role", default=DEFAULT_JOBS_ROLE)
    role_command.add_argument("--env-file", type=Path, default=Path(".env"))
    role_command.add_argument("--env-var", default="DATABASE_URL")
    related_command = commands.add_parser("related", parents=[shared], help="who is closest to an artist")
    related_command.add_argument("name", help="the artist, spelled any way")
    related_command.add_argument("--limit", type=int, default=20)
    evaluate_command = commands.add_parser(
        "evaluate", parents=[shared], help="backtest rankings against later same-room nights"
    )
    evaluate_command.add_argument(
        "--cutoff",
        type=date.fromisoformat,
        default=DEFAULT_CUTOFF,
        help="train before, test from (YYYY-MM-DD)",
    )
    evaluate_command.add_argument(
        "--variant",
        type=variant_argument,
        action="append",
        help="name:field=value[,field=value...] over the default scoring; repeatable",
    )
    evaluate_command.add_argument("--json", action="store_true", help="print one JSON object")
    movers_command = commands.add_parser(
        "movers", parents=[shared], help="whose related artists change most under new settings"
    )
    movers_command.add_argument(
        "--set",
        dest="settings",
        action="append",
        required=True,
        help="field=value over the default scoring; repeatable",
    )
    movers_command.add_argument("--top", type=int, default=10)
    movers_command.add_argument("--min-nights", type=int, default=5)
    movers_command.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
    elif args.command == "create-jobs-role":
        asyncio.run(set_up_jobs_role(args.role, args.env_file, args.env_var))
    elif args.command == "jobs":
        asyncio.run(run_nightly_jobs(args.store, args.max_pages, args.max_depth))
    elif args.command == "evaluate":
        asyncio.run(evaluate_rankings(args.cutoff, args.variant or default_variants(), args.json))
    elif args.command == "movers":
        try:
            overrides = parse_settings(args.settings)
        except ScoringSpecError as error:
            parser.error(str(error))
        asyncio.run(show_movers(overrides, args.top, args.min_nights, args.limit))
    else:
        return asyncio.run(show_related(args.name, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
