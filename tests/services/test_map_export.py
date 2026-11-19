import gzip
import json
import stat
from datetime import UTC, datetime, timedelta, timezone

import pytest

import soundshark.services.map_export as map_export
from soundshark.services.map_export import (
    MapCredit,
    MapRows,
    build_map,
    map_bytes,
    other_spellings,
    rounded_score,
    source_credits,
    write_map,
)
from tests.fakes import FakeSource
from tests.map_contract import assert_map_contract

GENERATED_AT = datetime(2031, 2, 3, 4, 5, 6, 789, tzinfo=UTC)
CREDITS = [MapCredit(name="Some Source", url="https://example.org/")]


def sample_rows(**overrides) -> MapRows:
    related = [(1, rank, 100 + rank, 0.5 / rank) for rank in range(1, 13)]
    related += [(100 + rank, 1, 1, 0.123456789) for rank in range(1, 13)]
    names = {1: "Ora Vance"} | {100 + rank: f"Guest {rank:02}" for rank in range(1, 13)} | {999: "Nobody"}
    rows = {
        "names": names,
        "aliases": {1: ["ora vance", "Ora Vance", "Ora V.", "ORA V.", "Oravance"]},
        "nights": {1: 53, 101: 4},
        "cities": {1: ["Lakeport", "Northvale"], 101: ["Northvale"]},
        "scene_of": {1: 3, 101: 3, 102: 8},
        "scenes": [(8, "Guest 02 / Guest 03 / Guest 04", 20), (3, "Ora Vance / Guest 01 / Guest 05", 412)],
        "related": related,
    }
    return MapRows(**(rows | overrides))


def test_the_map_has_exactly_the_contract_keys():
    assert_map_contract(build_map(sample_rows(), CREDITS, GENERATED_AT))


def test_the_contract_check_fails_when_a_field_is_added():
    tampered = json.loads(map_bytes(build_map(sample_rows(), CREDITS, GENERATED_AT)))
    tampered["artists"][0]["first_night"] = "2030-01-01"
    with pytest.raises(AssertionError):
        assert_map_contract(tampered)


def test_the_contract_check_fails_when_a_top_level_field_is_added():
    tampered = json.loads(map_bytes(build_map(sample_rows(), CREDITS, GENERATED_AT)))
    tampered["events"] = []
    with pytest.raises(AssertionError):
        assert_map_contract(tampered)


def test_the_header():
    payload = build_map(sample_rows(), CREDITS, GENERATED_AT.astimezone(timezone(timedelta(hours=2))))
    assert payload["version"] == 1
    assert payload["generated_at"] == "2031-02-03T04:05:06+00:00"
    assert payload["credits"] == CREDITS


def test_artists_carry_name_spellings_nights_and_scene():
    artists = {a["id"]: a for a in build_map(sample_rows(), CREDITS, GENERATED_AT)["artists"]}
    assert artists[1] == {
        "id": 1,
        "name": "Ora Vance",
        "aliases": ["ORA V.", "Oravance"],
        "nights": 53,
        "cities": ["Lakeport", "Northvale"],
        "scene": 3,
    }
    assert artists[103]["cities"] == []
    assert artists[103]["scene"] is None
    assert artists[103]["nights"] == 0
    assert 999 not in artists
    assert list(artists) == sorted(artists)


def test_related_is_the_top_ten_ordered_by_source_then_rank():
    related = build_map(sample_rows(), CREDITS, GENERATED_AT)["related"]
    from_one = [pair for pair in related if pair[0] == 1]
    assert [target for _, target, _ in from_one] == [100 + rank for rank in range(1, 11)]
    assert from_one[2] == [1, 103, 0.166667]
    assert [source for source, _, _ in related] == sorted(source for source, _, _ in related)
    assert [1, 101, 0.123457] not in related
    assert [101, 1, 0.123457] in related


def test_artists_outside_every_top_ten_are_still_listed():
    artists = {a["id"] for a in build_map(sample_rows(), CREDITS, GENERATED_AT)["artists"]}
    assert {111, 112} <= artists


def test_scenes_are_biggest_first():
    scenes = build_map(sample_rows(), CREDITS, GENERATED_AT)["scenes"]
    assert scenes == [
        {"id": 3, "label": "Ora Vance / Guest 01 / Guest 05", "size": 412},
        {"id": 8, "label": "Guest 02 / Guest 03 / Guest 04", "size": 20},
    ]


def test_other_spellings_skip_the_name_dedupe_and_cap():
    assert other_spellings("Mira", ["MIRA", "mira k", "Mira K", "Mira K.", "Mira K"]) == ["Mira K", "Mira K."]
    many = [f"Alias {n:02}" for n in range(30)]
    assert other_spellings("Mira", many) == many[:10]


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.0123456789, 0.0123457), (0.5, 0.5), (1.23456789e-7, 1.23457e-7), (12.3456789, 12.3457)],
)
def test_scores_keep_six_significant_digits(score, expected):
    assert rounded_score(score) == expected


def test_each_source_is_credited_by_name_and_origin():
    first = FakeSource(seed_pages=("events/2024", "other"))
    first.name = "first"
    second = FakeSource(seed_pages=())
    assert source_credits([first, second]) == [{"name": "first", "url": "https://site.test/"}]


def test_the_map_is_compact_utf8_json_with_an_equal_gzip(tmp_path):
    payload = build_map(sample_rows(names={**sample_rows().names, 1: "Öra Vancé"}), CREDITS, GENERATED_AT)
    path, gzip_path = write_map(payload, tmp_path / "nested" / "map" / "map.json")
    assert (path.name, gzip_path.name) == ("map.json", "map.json.gz")
    data = path.read_bytes()
    assert gzip.decompress(gzip_path.read_bytes()) == data
    assert json.loads(data) == payload
    assert "Öra Vancé".encode() in data
    assert b", " not in data and b": " not in data
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert sorted(p.name for p in path.parent.iterdir()) == ["map.json", "map.json.gz"]


def test_writing_twice_gives_the_same_bytes(tmp_path):
    payload = build_map(sample_rows(), CREDITS, GENERATED_AT)
    path, gzip_path = write_map(payload, tmp_path / "map.json")
    first = (path.read_bytes(), gzip_path.read_bytes())
    write_map(payload, tmp_path / "map.json")
    assert (path.read_bytes(), gzip_path.read_bytes()) == first


def test_a_failed_write_leaves_the_old_files_and_no_temporary_ones(tmp_path, monkeypatch):
    old = build_map(sample_rows(), CREDITS, GENERATED_AT)
    path, gzip_path = write_map(old, tmp_path / "map.json")
    before = (path.read_bytes(), gzip_path.read_bytes())

    def broken_compress(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(map_export.gzip, "compress", broken_compress)
    with pytest.raises(OSError, match="disk full"):
        write_map(build_map(sample_rows(nights={}), CREDITS, GENERATED_AT), path)
    assert (path.read_bytes(), gzip_path.read_bytes()) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["map.json", "map.json.gz"]


def test_scene_names_replace_the_labels_of_the_scenes_they_name():
    rows = sample_rows()
    named, *unnamed = sorted(rows.scenes, key=lambda scene: scene[0])
    scenes = build_map(rows, CREDITS, GENERATED_AT, {named[0]: "Night Drive", 999: "Gone"})["scenes"]
    labels = {scene["id"]: scene["label"] for scene in scenes}
    assert labels[named[0]] == "Night Drive"
    assert all(labels[scene_id] == label for scene_id, label, _ in unnamed)
    assert 999 not in labels


def test_scene_names_load_from_toml(tmp_path):
    names_file = tmp_path / "scene_names.toml"
    names_file.write_text('[names]\n3 = " Night Drive "\n12 = "Slow Burn"\n', encoding="utf-8")
    assert map_export.load_scene_names(names_file) == {3: "Night Drive", 12: "Slow Burn"}


@pytest.mark.parametrize(
    "body", ['[names]\nthree = "Night Drive"', '[names]\n3 = ""', "[names]\n3 = 7", 'names = "x"']
)
def test_bad_scene_names_are_refused(tmp_path, body):
    names_file = tmp_path / "scene_names.toml"
    names_file.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        map_export.load_scene_names(names_file)


def test_scene_names_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv(map_export.SCENE_NAMES_ENV_VAR, raising=False)
    assert map_export.scene_names_from_env() == {}
    names_file = tmp_path / "scene_names.toml"
    names_file.write_text('[names]\n5 = "Slow Burn"\n', encoding="utf-8")
    monkeypatch.setenv(map_export.SCENE_NAMES_ENV_VAR, str(names_file))
    assert map_export.scene_names_from_env() == {5: "Slow Burn"}


def test_the_history_folder_sits_next_to_the_map_folder(tmp_path):
    assert map_export.history_dir_for(tmp_path / "map" / "map.json") == tmp_path / "map-history"


def test_archived_maps_are_named_by_time_and_only_the_newest_are_kept(tmp_path):
    gzip_path = tmp_path / "map.json.gz"
    history = tmp_path / "map-history"
    archived = [
        map_export.archive_map(gzip_path, history, GENERATED_AT + timedelta(days=day), keep=3)
        for day in range(1, 5)
        if gzip_path.write_bytes(f"day {day}".encode())
    ]
    assert archived[-1].read_bytes() == b"day 4"
    kept = sorted(path.name for path in history.iterdir())
    assert len(kept) == 3
    assert kept[-1] == f"map-{(GENERATED_AT + timedelta(days=4)).astimezone(UTC):%Y%m%dT%H%M%SZ}.json.gz"
    assert (history / kept[0]).read_bytes() == b"day 2"


def test_archiving_keeps_at_least_one(tmp_path):
    with pytest.raises(ValueError):
        map_export.archive_map(tmp_path / "map.json.gz", tmp_path / "h", GENERATED_AT, keep=0)
