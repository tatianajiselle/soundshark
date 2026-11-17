import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations

from soundshark.models.graph_scoring import GraphScoring
from soundshark.services.artist_graph import (
    ArtistEdge,
    CreditOnBill,
    build_edges,
    nights_per_artist,
    related_artist_ids,
)
from soundshark.services.scoring_variants import ScoringVariant, SettingValue

COUNT_BASELINE_NAME = "count shared nights"
DEFAULTS_NAME = "defaults"
RECALL_DEPTH = 10
NEW_PARTNER_DEPTH = 50
HOME_ROOM_DEPTH = 10
HOME_ROOM_MIN_NIGHTS = 5

type HomeRoom = tuple[int, str]


@dataclass(frozen=True, slots=True)
class BacktestTargets:
    train_nights: int
    test_nights: int
    future_same_room_pairs: int
    future_partners: dict[int, set[int]]
    new_future_partners: dict[int, set[int]]
    nights_in_train: dict[int, int]
    home_rooms: dict[int, HomeRoom]


@dataclass(frozen=True, slots=True)
class RankingQuality:
    name: str
    overrides: dict[str, SettingValue]
    recall_at_10: float
    new_partner_recall_at_50: float
    home_room_share_at_10: float
    home_room_artists: int


@dataclass(frozen=True, slots=True)
class Backtest:
    cutoff: datetime
    train_nights: int
    test_nights: int
    future_same_room_pairs: int
    rankings: list[RankingQuality]


def split_at(
    credits: Iterable[CreditOnBill], cutoff: datetime
) -> tuple[list[CreditOnBill], list[CreditOnBill]]:
    train: list[CreditOnBill] = []
    test: list[CreditOnBill] = []
    for credit in credits:
        (train if credit.starts_at < cutoff else test).append(credit)
    return train, test


def same_room_partners(credits: Iterable[CreditOnBill]) -> dict[int, set[int]]:
    rooms: dict[tuple[int, str], set[int]] = defaultdict(set)
    for credit in credits:
        rooms[credit.event_id, credit.room].add(credit.artist_id)
    partners: dict[int, set[int]] = defaultdict(set)
    for artists in rooms.values():
        for a_id, b_id in combinations(artists, 2):
            partners[a_id].add(b_id)
            partners[b_id].add(a_id)
    return dict(partners)


def home_rooms(credits: Iterable[CreditOnBill]) -> dict[int, HomeRoom]:
    room_nights: dict[int, set[tuple[int, int, str]]] = defaultdict(set)
    for credit in credits:
        room_nights[credit.artist_id].add((credit.event_id, credit.venue_id, credit.room))
    homes: dict[int, HomeRoom] = {}
    for artist_id, nights in room_nights.items():
        counts = Counter((venue_id, room) for _, venue_id, room in nights)
        homes[artist_id] = min(counts, key=lambda home: (-counts[home], home))
    return homes


def backtest_targets(train: Sequence[CreditOnBill], test: Sequence[CreditOnBill]) -> BacktestTargets:
    nights_in_train = nights_per_artist(train)
    met_before = same_room_partners(train)
    future_partners: dict[int, set[int]] = {}
    new_future_partners: dict[int, set[int]] = {}
    for artist_id, partners in same_room_partners(test).items():
        if artist_id not in nights_in_train:
            continue
        known = {partner for partner in partners if partner in nights_in_train}
        if not known:
            continue
        future_partners[artist_id] = known
        new = known - met_before.get(artist_id, set())
        if new:
            new_future_partners[artist_id] = new
    return BacktestTargets(
        train_nights=len({c.event_id for c in train}),
        test_nights=len({c.event_id for c in test}),
        future_same_room_pairs=sum(len(partners) for partners in future_partners.values()) // 2,
        future_partners=future_partners,
        new_future_partners=new_future_partners,
        nights_in_train=nights_in_train,
        home_rooms=home_rooms(train),
    )


def recall(related: Mapping[int, Sequence[int]], targets: Mapping[int, set[int]], depth: int) -> float:
    found = 0
    possible = 0
    for artist_id, partners in targets.items():
        top = set(related.get(artist_id, [])[:depth])
        found += len(partners & top)
        possible += min(len(partners), depth)
    return found / possible if possible else 0.0


def home_room_share(related: Mapping[int, Sequence[int]], targets: BacktestTargets) -> tuple[float, int]:
    shares: list[float] = []
    for artist_id, ranked in related.items():
        if targets.nights_in_train.get(artist_id, 0) < HOME_ROOM_MIN_NIGHTS or len(ranked) < HOME_ROOM_DEPTH:
            continue
        home = targets.home_rooms[artist_id]
        top = ranked[:HOME_ROOM_DEPTH]
        shares.append(sum(targets.home_rooms.get(other) == home for other in top) / len(top))
    return (sum(shares) / len(shares) if shares else 0.0), len(shares)


def ranking_quality(
    name: str,
    overrides: dict[str, SettingValue],
    related: Mapping[int, Sequence[int]],
    targets: BacktestTargets,
) -> RankingQuality:
    share, artists = home_room_share(related, targets)
    return RankingQuality(
        name=name,
        overrides=overrides,
        recall_at_10=recall(related, targets.future_partners, RECALL_DEPTH),
        new_partner_recall_at_50=recall(related, targets.new_future_partners, NEW_PARTNER_DEPTH),
        home_room_share_at_10=share,
        home_room_artists=artists,
    )


def rank_by_shared_nights(edges: Iterable[ArtistEdge], how_many: int) -> dict[int, list[int]]:
    neighbours: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for edge in edges:
        neighbours[edge.a_id].append((edge.b_id, edge.shared_events))
        neighbours[edge.b_id].append((edge.a_id, edge.shared_events))
    return {
        artist_id: [other for other, _ in sorted(others, key=lambda o: (-o[1], o[0]))[:how_many]]
        for artist_id, others in neighbours.items()
    }


def count_baseline(train: Sequence[CreditOnBill], cutoff: datetime) -> dict[int, list[int]]:
    scoring = GraphScoring()
    return rank_by_shared_nights(build_edges(train, scoring, cutoff), scoring.related_per_artist)


async def backtest(
    credits: Iterable[CreditOnBill], cutoff: datetime, variants: Sequence[ScoringVariant]
) -> Backtest:
    train, test = split_at(credits, cutoff)
    targets = backtest_targets(train, test)
    baseline = await asyncio.to_thread(count_baseline, train, cutoff)
    rankings = [ranking_quality(COUNT_BASELINE_NAME, {}, baseline, targets)]
    for variant in [ScoringVariant(DEFAULTS_NAME, {}), *variants]:
        related = await asyncio.to_thread(related_artist_ids, train, variant.scoring, cutoff)
        rankings.append(ranking_quality(variant.name, variant.overrides, related, targets))
    return Backtest(
        cutoff=cutoff,
        train_nights=targets.train_nights,
        test_nights=targets.test_nights,
        future_same_room_pairs=targets.future_same_room_pairs,
        rankings=rankings,
    )
