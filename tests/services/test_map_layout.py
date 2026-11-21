import math

from soundshark.services.map_layout import LAYOUT_RADIUS, layout_3d, main_artists


def chain(start: int, length: int) -> list[tuple[int, int, int, float]]:
    return [(start + i, 1, start + i + 1, 0.5) for i in range(length - 1)]


def test_main_artists_drop_small_islands():
    ids = list(range(1, 201))
    related = chain(1, 197) + [(198, 1, 199, 0.5)]
    main = main_artists(ids, related)
    assert len(main) == 197
    assert 198 not in main and 200 not in main


def test_main_artists_fall_back_to_the_largest_component():
    ids = [1, 2, 3, 4, 5, 6, 7]
    related = chain(1, 5) + [(6, 1, 7, 0.5)]
    assert main_artists(ids, related) == [1, 2, 3, 4, 5]


def test_layout_places_the_main_artists_in_3d_around_the_centre():
    ids = list(range(1, 61))
    related = chain(1, 60) + [(1, 2, 30, 0.2), (10, 2, 50, 0.2)]
    positions = layout_3d(ids, related)
    assert sorted(positions) == ids
    assert all(len(point) == 3 for point in positions.values())
    for axis in range(3):
        assert abs(sum(point[axis] for point in positions.values()) / len(positions)) < 1.0
    spread = math.sqrt(sum(x * x + y * y + z * z for x, y, z in positions.values()) / len(positions))
    assert math.isclose(spread, LAYOUT_RADIUS, rel_tol=0.01)


def test_layout_is_the_same_every_time():
    ids = list(range(1, 41))
    related = chain(1, 40) + [(5, 2, 25, 0.3)]
    assert layout_3d(ids, related) == layout_3d(ids, related)


def test_layout_of_nothing_is_empty():
    assert layout_3d([], []) == {}
