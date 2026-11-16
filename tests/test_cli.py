import pytest
import structlog

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
