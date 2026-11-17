import pytest

from soundshark.services.ranking_changes import list_change, ranking_changes

NAMES = {
    1: "Selene Mau",
    2: "Ora Vance",
    3: "Juno Hale",
    10: "Ilsa Brook",
    11: "Tamsin Rhee",
    12: "Cato Wren",
}


def test_change_is_one_minus_overlap_over_union():
    assert list_change([1, 2, 3], [2, 3, 4]) == pytest.approx(0.5)
    assert list_change([1, 2], [2, 1]) == 0.0
    assert list_change([], []) == 0.0
    assert list_change([1], [2]) == 1.0


def test_biggest_movers_first_then_busier_artists_then_names():
    before = {1: [10, 11], 2: [10, 11], 3: [10, 11], 4: [10], 5: [10, 11]}
    after = {1: [10, 12], 2: [12, 10], 3: [10, 12], 4: [12], 5: [11, 10]}
    nights = {1: 8, 2: 10, 3: 10, 4: 2, 5: 30}
    changes = ranking_changes(before, after, nights, NAMES, top=10, min_nights=5)
    assert [c.name for c in changes] == ["Juno Hale", "Ora Vance", "Selene Mau", "#5"]
    assert [c.change for c in changes] == [pytest.approx(2 / 3)] * 3 + [0.0]
    juno = changes[0]
    assert (juno.artist_id, juno.nights, juno.entered, juno.left) == (3, 10, ["Cato Wren"], ["Tamsin Rhee"])


def test_only_the_top_of_each_list_is_compared():
    before = {1: [10, 11, 12]}
    after = {1: [10, 11, 2]}
    [change] = ranking_changes(before, after, {1: 5}, NAMES, top=2, min_nights=5)
    assert (change.change, change.entered, change.left) == (0.0, [], [])
