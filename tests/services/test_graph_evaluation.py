from datetime import UTC, datetime, timedelta

import pytest

from soundshark.services.artist_graph import ArtistEdge, CreditOnBill
from soundshark.services.graph_evaluation import (
    BacktestTargets,
    backtest,
    backtest_targets,
    home_room_share,
    rank_by_shared_nights,
    recall,
    split_at,
)
from soundshark.services.scoring_variants import parse_variant

CUTOFF = datetime(2025, 6, 1, tzinfo=UTC)


def credit(artist: int, event: int, room: str = "Main", venue: int = 1) -> CreditOnBill:
    starts_at = CUTOFF + timedelta(days=event - 10)
    return CreditOnBill(artist, event, starts_at, room, artist * 1000 + event, venue)


TRAIN = [credit(1, 1), credit(2, 1), credit(3, 1, room="Annex"), credit(1, 2), credit(3, 2)]
TEST = [
    credit(1, 10),
    credit(2, 10),
    credit(3, 10),
    credit(4, 10, room="Annex"),
    credit(2, 11),
    credit(5, 11),
]


def test_split_puts_the_cutoff_night_in_the_test_set():
    train, test = split_at(TRAIN + TEST, CUTOFF)
    assert train == TRAIN
    assert test == TEST


def test_targets_are_later_same_room_partners_among_artists_already_known():
    targets = backtest_targets(TRAIN, TEST)
    assert (targets.train_nights, targets.test_nights, targets.future_same_room_pairs) == (2, 2, 3)
    assert targets.future_partners == {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
    assert targets.new_future_partners == {2: {3}, 3: {2}}
    assert targets.nights_in_train == {1: 2, 2: 1, 3: 2}


def test_home_room_is_the_most_played_room_per_venue_with_ties_broken_by_name():
    targets = backtest_targets([*TRAIN, credit(2, 3, room="Main", venue=2)], TEST)
    assert targets.home_rooms == {1: (1, "Main"), 2: (1, "Main"), 3: (1, "Annex")}


def test_recall_counts_hits_against_at_most_depth_partners():
    partners = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
    related = {1: [2, 9], 2: [9, 8], 3: [1, 2]}
    assert recall(related, partners, depth=10) == pytest.approx(3 / 6)
    assert recall({1: [3, 2]}, {1: {2, 3}}, depth=1) == 1.0
    assert recall({}, {}, depth=10) == 0.0


def test_home_room_share_only_scores_regulars_with_a_full_list():
    main, annex = (1, "Main"), (1, "Annex")
    others = list(range(100, 110))
    homes = {1: main, 2: main, 3: main, 4: annex}
    homes |= {other: main if other < 104 else annex for other in others}
    targets = BacktestTargets(
        train_nights=0,
        test_nights=0,
        future_same_room_pairs=0,
        future_partners={},
        new_future_partners={},
        nights_in_train={1: 5, 2: 5, 3: 4, 4: 9},
        home_rooms=homes,
    )
    related = {1: others, 2: others[:9], 3: others, 4: others}
    assert home_room_share(related, targets) == (pytest.approx((0.4 + 0.6) / 2), 2)


def test_count_baseline_ranks_direct_neighbours_by_shared_nights():
    edges = [
        ArtistEdge(1, 2, shared_events=1),
        ArtistEdge(1, 3, shared_events=3),
        ArtistEdge(1, 4, shared_events=1),
        ArtistEdge(2, 3, shared_events=2),
    ]
    assert rank_by_shared_nights(edges, how_many=10)[1] == [3, 2, 4]
    assert rank_by_shared_nights(edges, how_many=2) == {1: [3, 2], 2: [3, 1], 3: [1, 2], 4: [1]}


async def test_backtest_scores_the_baseline_the_defaults_and_each_variant():
    result = await backtest(TRAIN + TEST, CUTOFF, [parse_variant("floor-1:room_profile_floor=1.0")])
    assert (result.train_nights, result.test_nights, result.future_same_room_pairs) == (2, 2, 3)
    assert [r.name for r in result.rankings] == ["count shared nights", "defaults", "floor-1"]
    assert result.rankings[2].overrides == {"room_profile_floor": 1.0}
    for ranking in result.rankings:
        assert ranking.recall_at_10 == 1.0
        assert ranking.new_partner_recall_at_50 == 1.0
        assert (ranking.home_room_share_at_10, ranking.home_room_artists) == (0.0, 0)
