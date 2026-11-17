import math
from datetime import UTC, datetime, timedelta

import networkx as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from soundshark.models.graph_scoring import GraphScoring
from soundshark.services.artist_graph import (
    ArtistEdge,
    CreditOnBill,
    build_edges,
    recency_factor,
    room_profile_similarity,
    top_related_by_pagerank,
)

NOW = datetime(2026, 11, 16, tzinfo=UTC)
NO_DECAY = GraphScoring(recency_half_life_years=1e9, night_count_padding=0, room_profile_floor=1.0)


def credit(
    artist: int,
    event: int,
    room: str = "Main",
    slot: int | None = None,
    years_ago: float = 0,
    venue: int = 1,
):
    starts_at = NOW - timedelta(days=years_ago * 365.25)
    slot_id = slot if slot is not None else artist * 1000 + event
    return CreditOnBill(artist, event, starts_at, room, slot_id, venue)


def edge_between(edges: list[ArtistEdge], a: int, b: int) -> ArtistEdge:
    return next(e for e in edges if (e.a_id, e.b_id) == (min(a, b), max(a, b)))


def test_b2b_beats_same_room_beats_same_night():
    credits = [
        credit(1, 10, slot=99),
        credit(2, 10, slot=99),
        credit(3, 10, room="Main"),
        credit(4, 10, room="Annex"),
    ]
    edges = build_edges(credits, NO_DECAY, NOW)
    b2b, same_room, same_night = (
        edge_between(edges, 1, 2),
        edge_between(edges, 1, 3),
        edge_between(edges, 1, 4),
    )
    assert (b2b.b2b, b2b.same_room, b2b.shared_events) == (1, 1, 1)
    assert (same_room.b2b, same_room.same_room) == (0, 1)
    assert (same_night.b2b, same_night.same_room) == (0, 0)
    assert b2b.weight == pytest.approx(4.0)
    assert same_room.weight == pytest.approx(3.0)
    assert same_night.weight == pytest.approx(0.25)


def test_a_pair_counts_once_per_night_even_across_rooms():
    credits = [credit(1, 10, room="Main"), credit(1, 10, room="Annex", slot=5), credit(2, 10, room="Annex")]
    [edge] = build_edges(credits, NO_DECAY, NOW)
    assert edge.shared_events == 1
    assert edge.same_room == 1


def test_busy_artists_are_divided_by_how_often_they_play():
    credits = [credit(1, 10), credit(2, 10)] + [credit(1, event) for event in range(11, 14)]
    [edge] = build_edges(credits, NO_DECAY, NOW)
    assert edge.weight == pytest.approx(3.0 / math.sqrt(4 * 1))


def test_padding_keeps_one_night_guests_from_outranking_regulars():
    busy_artist = [credit(1, event) for event in range(20)]
    regular = [credit(2, event) for event in range(5)] + [credit(2, event) for event in range(100, 130)]
    one_night_guest = [credit(3, 0)]
    credits = busy_artist + regular + one_night_guest

    def ranking(padding: float) -> list[int]:
        scoring = GraphScoring(recency_half_life_years=1e9, night_count_padding=padding)
        related = top_related_by_pagerank(build_edges(credits, scoring, NOW), scoring)
        return [other for other, _ in related[1]]

    assert ranking(padding=0) == [3, 2]
    assert ranking(padding=5) == [2, 3]


ROOM_PROFILES = GraphScoring(recency_half_life_years=1e9, night_count_padding=0, room_profile_floor=0.25)


def test_room_profile_similarity():
    assert room_profile_similarity({"Main": 3}, {"Main": 1}) == pytest.approx(1.0)
    assert room_profile_similarity({"Main": 3}, {"Annex": 2}) == 0.0
    assert room_profile_similarity({"Main": 1, "Annex": 1}, {"Main": 1}) == pytest.approx(1 / math.sqrt(2))


def test_a_shared_room_counts_less_when_one_artist_usually_plays_another_room():
    main_regular, also_main, usually_annex = 1, 2, 3
    credits = [credit(main_regular, 10), credit(also_main, 10), credit(usually_annex, 10)]
    credits += [credit(main_regular, event) for event in range(11, 15)]
    credits += [credit(also_main, event) for event in range(21, 25)]
    credits += [credit(usually_annex, event, room="Annex") for event in range(31, 35)]

    edges = build_edges(credits, ROOM_PROFILES, NOW)
    regular_pair = edge_between(edges, main_regular, also_main)
    mixed_pair = edge_between(edges, main_regular, usually_annex)

    assert regular_pair.same_room == mixed_pair.same_room == 1
    assert regular_pair.weight == pytest.approx(3.0 / 5)
    similarity = 1 / math.sqrt(1 + 4 * 4)
    assert mixed_pair.weight == pytest.approx(3.0 * (0.25 + 0.75 * similarity) / 5)


def test_room_profiles_only_compare_rooms_at_the_venue_of_the_night():
    credits = [credit(1, 10), credit(2, 10)]
    credits += [credit(2, event, room="Annex", venue=2) for event in range(11, 15)]
    [edge] = build_edges(credits, ROOM_PROFILES, NOW)
    assert edge.weight == pytest.approx(3.0 / math.sqrt(1 * 5))


def test_old_nights_count_half_after_the_half_life():
    assert recency_factor(NOW - timedelta(days=3 * 365.25), NOW, 3.0) == pytest.approx(0.5)
    assert recency_factor(NOW + timedelta(days=30), NOW, 3.0) == 1.0


def test_first_and_last_night_together():
    credits = [
        credit(1, 10, years_ago=5),
        credit(2, 10, years_ago=5),
        credit(1, 11, years_ago=1),
        credit(2, 11, years_ago=1),
    ]
    [edge] = build_edges(credits, NO_DECAY, NOW)
    assert edge.first_together is not None and edge.last_together is not None
    assert (NOW - edge.first_together).days == 1826
    assert (NOW - edge.last_together).days == 365


def test_two_hop_neighbours_are_related_without_sharing_a_night():
    edges = [ArtistEdge(1, 2, weight=4.0), ArtistEdge(2, 3, weight=5.0), ArtistEdge(4, 5, weight=1.0)]
    related = top_related_by_pagerank(edges, GraphScoring())
    assert [other for other, _ in related[1]] == [2, 3]
    assert all(score > 0 for _, score in related[1])
    assert 4 not in dict(related[1]) and 5 not in dict(related[1])


def test_keeps_at_most_the_configured_number_and_never_the_artist_itself():
    star = [ArtistEdge(0, n, weight=float(n)) for n in range(1, 30)]
    related = top_related_by_pagerank(star, GraphScoring(related_per_artist=5))
    assert len(related[0]) == 5
    assert [other for other, _ in related[0]] == [29, 28, 27, 26, 25]
    assert all(other != 0 for other, _ in related[0])


@settings(max_examples=25, deadline=None)
@given(
    weighted_pairs=st.dictionaries(
        st.tuples(st.integers(0, 14), st.integers(0, 14)).filter(lambda pair: pair[0] < pair[1]),
        st.floats(0.1, 10),
        min_size=1,
        max_size=40,
    )
)
def test_scores_match_networkx_personalized_pagerank(weighted_pairs):
    edges = [ArtistEdge(a, b, weight=w) for (a, b), w in weighted_pairs.items()]
    scoring = GraphScoring(related_per_artist=1000)
    ours = top_related_by_pagerank(edges, scoring, sources_per_batch=4)

    graph = nx.Graph()
    graph.add_weighted_edges_from((e.a_id, e.b_id, e.weight) for e in edges)
    for source in graph.nodes:
        expected = nx.pagerank(
            graph,
            alpha=scoring.pagerank_damping,
            personalization={source: 1.0},
            nstart={source: 1.0},
            tol=1e-13,
            max_iter=2000,
        )
        expected.pop(source)
        assert dict(ours[source]) == pytest.approx({n: s for n, s in expected.items() if s > 0}, abs=1e-9)
