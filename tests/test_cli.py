import pytest
import structlog

import soundshark.__main__ as cli
from soundshark.__main__ import build_parser, main


@pytest.fixture(autouse=True)
def restore_default_logging():
    yield
    structlog.reset_defaults()


def test_crawl_options_are_parsed():
    args = build_parser().parse_args(
        ["crawl", "--max-pages", "5", "--max-depth", "1", "--store", "elsewhere", "-v"]
    )
    assert args.command == "crawl"
    assert (args.max_pages, args.max_depth, str(args.store), args.verbose) == (5, 1, "elsewhere", True)


def test_identify_rebuild_flag():
    assert build_parser().parse_args(["identify", "--rebuild"]).rebuild is True
    assert build_parser().parse_args(["identify"]).rebuild is False


def test_jobs_takes_the_crawl_limits():
    args = build_parser().parse_args(["jobs", "--max-pages", "5", "--store", "elsewhere"])
    assert (args.command, args.max_pages, args.max_depth, str(args.store)) == ("jobs", 5, None, "elsewhere")


def test_jobs_run_every_step_in_order(tmp_path, monkeypatch):
    steps: list[str] = []

    async def record(step: str) -> None:
        steps.append(step)

    monkeypatch.setattr(cli, "crawl_all_sources", lambda store, pages, depth: record("crawl"))
    monkeypatch.setattr(cli, "ingest_all_sources", lambda store: record("ingest"))
    monkeypatch.setattr(cli, "identify_artists", lambda rebuild: record(f"identify rebuild={rebuild}"))
    monkeypatch.setattr(cli, "rebuild_graph", lambda: record("graph"))
    assert main(["jobs", "--store", str(tmp_path)]) == 0
    assert steps == ["crawl", "ingest", "identify rebuild=False", "graph"]


def test_jobs_stop_at_the_first_failing_step(tmp_path, monkeypatch):
    steps: list[str] = []

    async def record(step: str) -> None:
        steps.append(step)

    async def fail(store: object) -> None:
        raise RuntimeError("ingest broke")

    monkeypatch.setattr(cli, "crawl_all_sources", lambda store, pages, depth: record("crawl"))
    monkeypatch.setattr(cli, "ingest_all_sources", fail)
    monkeypatch.setattr(cli, "identify_artists", lambda rebuild: record("identify"))
    monkeypatch.setattr(cli, "rebuild_graph", lambda: record("graph"))
    with pytest.raises(RuntimeError, match="ingest broke"):
        main(["jobs", "--store", str(tmp_path)])
    assert steps == ["crawl"]


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_crawl_command_saves_the_demo_site_into_the_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOUNDSHARK_SOURCES", raising=False)
    store_dir = tmp_path / "data"
    assert main(["crawl", "--store", str(store_dir)]) == 0
    assert len(list((store_dir / "raw" / "demo").iterdir())) == 3
    assert len(list((store_dir / "runs" / "demo").iterdir())) == 1
