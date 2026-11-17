import random
from dataclasses import replace

import pytest

from soundshark.models.scene_settings import SceneSettings
from soundshark.services.scenes import (
    detect_scenes,
    find_communities,
    match_scene_ids,
    related_graph,
    scene_label,
)

SETTINGS = SceneSettings(min_scene_size=5)


def planted_related(
    group_sizes: list[int], *, seed: int = 1, per_artist: int = 12, cross_links: int = 2, start_id: int = 1
) -> tuple[dict[int, list[tuple[int, float]]], list[frozenset[int]]]:
    rng = random.Random(seed)
    groups: list[list[int]] = []
    next_id = start_id
    for size in group_sizes:
        groups.append(list(range(next_id, next_id + size)))
        next_id += size
    everyone = [artist for group in groups for artist in group]
    ranked: dict[int, list[tuple[int, float]]] = {}
    for group in groups:
        for artist in group:
            mates = rng.sample([a for a in group if a != artist], min(per_artist, len(group) - 1))
            strangers = rng.sample([a for a in everyone if a not in group], cross_links)
            rows = [(other, rng.uniform(0.02, 0.05)) for other in mates]
            rows += [(other, rng.uniform(0.001, 0.004)) for other in strangers]
            ranked[artist] = sorted(rows, key=lambda row: -row[1])
    return ranked, [frozenset(group) for group in groups]


def no_names(ranked):
    return {artist: f"Artist {artist:04}" for artist in ranked}


def membership(scenes) -> dict[int, int]:
    return {artist: scene.id for scene in scenes for artist in scene.members}


def test_planted_communities_are_recovered():
    ranked, groups = planted_related([40, 30, 25, 20])
    scenes = detect_scenes(ranked, {}, {}, no_names(ranked), SETTINGS)
    assert sorted(scene.members for scene in scenes) == sorted(groups)
    assert [scene.id for scene in scenes] == [1, 2, 3, 4]
    assert [len(scene.members) for scene in scenes] == [40, 30, 25, 20]


def test_the_same_input_gives_the_same_scenes():
    ranked, _ = planted_related([30, 30, 30], cross_links=4)
    shuffled = dict(sorted(ranked.items(), key=lambda item: -item[0]))
    first = detect_scenes(ranked, {}, {}, no_names(ranked), SETTINGS)
    again = detect_scenes(shuffled, {}, {}, no_names(ranked), SETTINGS)
    assert first == again


def test_ids_stay_put_when_the_graph_changes_a_little():
    ranked, _ = planted_related([40, 30, 25, 20])
    first = detect_scenes(ranked, {}, {}, no_names(ranked), SETTINGS)
    previous = {scene.id: scene.members for scene in first}
    rng = random.Random(9)
    leaving = 3
    changed = {
        artist: sorted(
            [(other, score * rng.uniform(0.95, 1.05)) for other, score in rows if other != leaving],
            key=lambda row: -row[1],
        )
        for artist, rows in ranked.items()
        if artist != leaving
    }
    second = detect_scenes(changed, previous, {}, no_names(changed), SETTINGS)
    before, after = membership(first), membership(second)
    assert {after[artist] for artist in after} == set(previous)
    assert all(after[artist] == before[artist] for artist in after)


def test_rerunning_with_no_changes_keeps_every_id():
    ranked, _ = planted_related([30, 20, 20])
    first = detect_scenes(ranked, {}, {}, no_names(ranked), SETTINGS)
    renumbered = {scene.id + 100: scene.members for scene in first}
    second = detect_scenes(ranked, renumbered, {}, no_names(ranked), SETTINGS)
    assert sorted((scene.id, scene.members) for scene in second) == sorted(renumbered.items())


def test_a_split_keeps_the_id_for_the_bigger_part_and_gives_the_other_a_new_one():
    big, small, other = frozenset(range(1, 31)), frozenset(range(31, 46)), frozenset(range(100, 120))
    previous = {4: big | small, 9: other}
    assert match_scene_ids([big, other, small], previous, 0.3) == [4, 9, 10]


def test_a_merge_keeps_the_id_with_the_biggest_overlap_and_retires_the_other():
    first, second = frozenset(range(1, 31)), frozenset(range(31, 51))
    unrelated = frozenset(range(200, 220))
    previous = {2: first, 5: second}
    assert match_scene_ids([first | second, unrelated], previous, 0.3) == [2, 6]


def test_a_retired_id_is_never_handed_to_another_scene_in_the_same_run():
    retired, kept = frozenset(range(1, 21)), frozenset(range(21, 41))
    previous = {7: retired, 3: kept}
    newcomers = [kept, frozenset(range(500, 520)), frozenset(range(600, 620))]
    assigned = match_scene_ids(newcomers, previous, 0.3)
    assert assigned == [3, 8, 9]
    assert 7 not in assigned


def test_too_little_overlap_gets_a_new_id():
    previous = {1: frozenset(range(1, 41))}
    drifted = frozenset(range(30, 70))
    assert match_scene_ids([drifted], previous, 0.3) == [2]
    assert match_scene_ids([drifted], previous, 0.15) == [1]


def test_overlap_breaks_ties_before_jaccard():
    previous = {1: frozenset(range(1, 201)), 2: frozenset(range(201, 231))}
    straddling = frozenset(range(151, 231))
    assert match_scene_ids([straddling], previous, 0.2) == [1]


def test_first_ids_start_at_one():
    assert match_scene_ids([frozenset({1, 2}), frozenset({3})], {}, 0.3) == [1, 2]


def test_tiny_communities_get_no_scene():
    ranked, groups = planted_related([40, 30, 25], cross_links=1)
    island, _ = planted_related([4], per_artist=3, cross_links=0, start_id=1000)
    ranked |= island
    scenes = detect_scenes(ranked, {}, {}, no_names(ranked), SETTINGS)
    placed = membership(scenes)
    assert sorted(scene.members for scene in scenes) == sorted(groups)
    assert not set(island) & set(placed)


def test_the_label_is_the_three_most_booked_members_ties_by_name():
    members = frozenset({1, 2, 3, 4, 5})
    nights = {1: 4, 2: 9, 3: 4, 4: 12, 5: 1}
    names = {1: "zola", 2: "Mika", 3: "Arlo", 4: "Wren", 5: "Bex"}
    assert scene_label(members, nights, names) == "Wren / Mika / Arlo"


def test_scenes_are_labelled_by_their_busiest_members():
    ranked, groups = planted_related([20, 20])
    names = no_names(ranked)
    nights = {artist: 1 for artist in ranked} | {5: 30, 7: 20, 9: 20, 25: 40}
    scenes = detect_scenes(ranked, {}, nights, names, SETTINGS)
    labels = {scene.members: scene.label for scene in scenes}
    assert labels[groups[0]] == "Artist 0005 / Artist 0007 / Artist 0009"
    assert labels[groups[1]].startswith("Artist 0025 / ")


def test_the_graph_uses_the_top_k_and_adds_both_directions():
    ranked = {
        1: [(2, 0.3), (3, 0.1), (4, 0.05)],
        2: [(1, 0.2), (3, 0.2)],
        3: [(3, 0.5), (1, 0.4)],
    }
    graph = related_graph(ranked, top=2)
    assert sorted(graph.nodes) == [1, 2, 3]
    assert graph[1][2]["weight"] == pytest.approx(0.75 + 0.5)
    assert graph[1][3]["weight"] == pytest.approx(0.25 + 1.0)
    assert graph[2][3]["weight"] == pytest.approx(0.5)
    assert not graph.has_edge(3, 3)


def test_every_artist_gets_an_equal_say_whatever_its_scores():
    loud = {1: [(2, 100.0), (3, 100.0)], 2: [(1, 0.001)], 3: [(1, 0.001)]}
    graph = related_graph(loud, top=10)
    assert graph[1][2]["weight"] == pytest.approx(1.5)
    assert graph[1][3]["weight"] == pytest.approx(1.5)


def test_without_consensus_runs_leiden_still_finds_the_groups():
    ranked, groups = planted_related([30, 25, 20])
    communities = find_communities(related_graph(ranked, 10), replace(SETTINGS, consensus_runs=1))
    assert sorted(communities) == sorted(groups)


def test_no_related_artists_means_no_scenes():
    assert detect_scenes({}, {1: frozenset({1, 2})}, {}, {}, SETTINGS) == []


def test_an_emptied_scene_still_counts_when_picking_new_ids():
    assert match_scene_ids([frozenset({1, 2, 3})], {5: frozenset(), 2: frozenset({9})}, 0.3) == [6]
