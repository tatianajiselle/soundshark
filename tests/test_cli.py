from datetime import date

import pytest
import structlog

import soundshark.__main__ as cli
from soundshark.__main__ import build_parser, main
from soundshark.models.scene_settings import SceneSettings


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
    monkeypatch.setattr(cli, "assign_scenes", lambda settings: record(f"scenes {settings}"))
    assert main(["jobs", "--store", str(tmp_path)]) == 0
    assert steps == [
        "crawl",
        "ingest",
        "identify rebuild=False",
        "graph",
        f"scenes {SceneSettings()}",
    ]


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
    monkeypatch.setattr(cli, "assign_scenes", lambda settings: record("scenes"))
    with pytest.raises(RuntimeError, match="ingest broke"):
        main(["jobs", "--store", str(tmp_path)])
    assert steps == ["crawl"]


def test_scenes_options_default_to_the_scene_settings(monkeypatch):
    received: list[SceneSettings] = []

    async def record(settings: SceneSettings) -> None:
        received.append(settings)

    monkeypatch.setattr(cli, "assign_scenes", record)
    assert main(["scenes"]) == 0
    assert main(["scenes", "--top", "15", "--resolution", "2", "--min-size", "30"]) == 0
    assert received == [
        SceneSettings(),
        SceneSettings(related_per_artist=15, resolution=2.0, min_scene_size=30),
    ]


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


def test_evaluate_options_are_parsed():
    args = build_parser().parse_args(
        ["evaluate", "--cutoff", "2024-01-31", "--variant", "flat:room_profile_floor=1", "--json"]
    )
    assert args.cutoff == date(2024, 1, 31)
    assert [(v.name, v.overrides) for v in args.variant] == [("flat", {"room_profile_floor": 1.0})]
    assert args.json is True
    defaults = build_parser().parse_args(["evaluate"])
    assert (defaults.cutoff, defaults.variant, defaults.json) == (date(2025, 6, 1), None, False)


def test_evaluate_refuses_an_unknown_setting(capsys):
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["evaluate", "--variant", "typo:room_floor=1"])
    assert exit_info.value.code == 2
    assert "unknown setting 'room_floor'" in capsys.readouterr().err


def test_movers_options_are_parsed():
    args = build_parser().parse_args(["movers", "--set", "b2b_weight=2", "--set", "related_per_artist=20"])
    assert args.settings == ["b2b_weight=2", "related_per_artist=20"]
    assert (args.top, args.min_nights, args.limit) == (10, 5, 20)


def test_movers_needs_a_setting():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["movers"])


def test_movers_refuses_a_bad_value_before_touching_the_database(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["movers", "--set", "related_per_artist=many"])
    assert exit_info.value.code == 2
    assert "related_per_artist='many' is not a valid int" in capsys.readouterr().err
