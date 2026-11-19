import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations

import numpy as np
from scipy import sparse

from soundshark.models.graph_scoring import GraphScoring

SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class CreditOnBill:
    artist_id: int
    event_id: int
    starts_at: datetime
    room: str
    lineup_slot_id: int
    venue_id: int = 0


@dataclass(slots=True)
class ArtistEdge:
    a_id: int
    b_id: int
    shared_events: int = 0
    same_room: int = 0
    b2b: int = 0
    first_together: datetime | None = None
    last_together: datetime | None = None
    weight: float = 0.0


@dataclass(slots=True)
class _ArtistOnNight:
    rooms: set[str] = field(default_factory=set)
    lineup_slot_ids: set[int] = field(default_factory=set)


def recency_factor(starts_at: datetime, now: datetime, half_life_years: float) -> float:
    age_years = max(0.0, (now - starts_at).total_seconds() / SECONDS_PER_YEAR)
    return 0.5 ** (age_years / half_life_years)


def room_profile_similarity(a: dict[str, int], b: dict[str, int]) -> float:
    shared = sum(count * b.get(room, 0) for room, count in a.items())
    if shared == 0:
        return 0.0
    length_a = math.sqrt(sum(count * count for count in a.values()))
    length_b = math.sqrt(sum(count * count for count in b.values()))
    return shared / (length_a * length_b)


def build_edges(credits: Iterable[CreditOnBill], scoring: GraphScoring, now: datetime) -> list[ArtistEdge]:
    nights: dict[int, dict[int, _ArtistOnNight]] = defaultdict(lambda: defaultdict(_ArtistOnNight))
    starts_at_by_event: dict[int, datetime] = {}
    venue_by_event: dict[int, int] = {}
    for credit in credits:
        on_night = nights[credit.event_id][credit.artist_id]
        on_night.rooms.add(credit.room)
        on_night.lineup_slot_ids.add(credit.lineup_slot_id)
        starts_at_by_event[credit.event_id] = credit.starts_at
        venue_by_event[credit.event_id] = credit.venue_id

    room_nights: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for event_id, artists in nights.items():
        for artist_id, on_night in artists.items():
            for room in on_night.rooms:
                room_nights[artist_id, venue_by_event[event_id]][room] += 1

    room_fit_cache: dict[tuple[int, int, int], float] = {}

    def room_fit(a_id: int, b_id: int, venue_id: int) -> float:
        key = (a_id, b_id, venue_id)
        if key not in room_fit_cache:
            similarity = room_profile_similarity(room_nights[a_id, venue_id], room_nights[b_id, venue_id])
            floor = scoring.room_profile_floor
            room_fit_cache[key] = floor + (1 - floor) * similarity
        return room_fit_cache[key]

    nights_played: dict[int, int] = defaultdict(int)
    edges: dict[tuple[int, int], ArtistEdge] = {}
    for event_id, artists in nights.items():
        starts_at = starts_at_by_event[event_id]
        venue_id = venue_by_event[event_id]
        recency = recency_factor(starts_at, now, scoring.recency_half_life_years)
        for artist_id in artists:
            nights_played[artist_id] += 1
        for a_id, b_id in combinations(sorted(artists), 2):
            a, b = artists[a_id], artists[b_id]
            edge = edges.setdefault((a_id, b_id), ArtistEdge(a_id, b_id))
            edge.shared_events += 1
            if a.lineup_slot_ids & b.lineup_slot_ids:
                edge.b2b += 1
                edge.same_room += 1
                night_weight = scoring.b2b_weight
            elif a.rooms & b.rooms:
                edge.same_room += 1
                night_weight = scoring.same_room_weight
            else:
                night_weight = scoring.same_night_weight
            edge.weight += night_weight * recency * room_fit(a_id, b_id, venue_id)
            if edge.first_together is None or starts_at < edge.first_together:
                edge.first_together = starts_at
            if edge.last_together is None or starts_at > edge.last_together:
                edge.last_together = starts_at

    for edge in edges.values():
        padded_a = nights_played[edge.a_id] + scoring.night_count_padding
        padded_b = nights_played[edge.b_id] + scoring.night_count_padding
        edge.weight /= math.sqrt(padded_a * padded_b)
    return sorted(edges.values(), key=lambda e: (e.a_id, e.b_id))


def top_related_by_pagerank(
    edges: Sequence[ArtistEdge],
    scoring: GraphScoring,
    *,
    sources_per_batch: int = 256,
    tolerance: float = 1e-10,
    max_iterations: int = 600,
) -> dict[int, list[tuple[int, float]]]:
    artist_ids = sorted({e.a_id for e in edges} | {e.b_id for e in edges})
    if not artist_ids:
        return {}
    index_of = {artist_id: index for index, artist_id in enumerate(artist_ids)}
    walk_matrix = _transposed_walk_matrix(edges, index_of)
    artist_count = len(artist_ids)
    related: dict[int, list[tuple[int, float]]] = {}

    for batch_start in range(0, artist_count, sources_per_batch):
        sources = np.arange(batch_start, min(batch_start + sources_per_batch, artist_count))
        restart = np.zeros((artist_count, len(sources)))
        restart[sources, np.arange(len(sources))] = 1.0
        scores = _power_iteration(walk_matrix, restart, scoring.pagerank_damping, tolerance, max_iterations)
        for column, source in enumerate(sources.tolist()):
            related[artist_ids[source]] = _best_others(
                scores[:, column], source, artist_ids, scoring.related_per_artist
            )
    return related


def nights_per_artist(credits: Iterable[CreditOnBill]) -> dict[int, int]:
    nights: dict[int, set[int]] = defaultdict(set)
    for credit in credits:
        nights[credit.artist_id].add(credit.event_id)
    return {artist_id: len(events) for artist_id, events in nights.items()}


def related_artist_ids(
    credits: Iterable[CreditOnBill], scoring: GraphScoring, now: datetime
) -> dict[int, list[int]]:
    related = top_related_by_pagerank(build_edges(credits, scoring, now), scoring)
    return {artist_id: [other_id for other_id, _ in ranked] for artist_id, ranked in related.items()}


def _transposed_walk_matrix(edges: Sequence[ArtistEdge], index_of: dict[int, int]) -> sparse.csr_array:
    rows = [index_of[e.a_id] for e in edges] + [index_of[e.b_id] for e in edges]
    columns = [index_of[e.b_id] for e in edges] + [index_of[e.a_id] for e in edges]
    weights = [e.weight for e in edges] * 2
    size = len(index_of)
    adjacency = sparse.csr_array((weights, (rows, columns)), shape=(size, size))
    out_weight = np.asarray(adjacency.sum(axis=1)).ravel()
    out_weight[out_weight == 0] = 1.0
    step_probabilities = sparse.diags_array(1.0 / out_weight) @ adjacency
    return sparse.csr_array(step_probabilities.T)


def _power_iteration(
    walk_matrix: sparse.csr_array, restart: np.ndarray, damping: float, tolerance: float, max_iterations: int
) -> np.ndarray:
    scores = restart.copy()
    for _ in range(max_iterations):
        next_scores = damping * (walk_matrix @ scores) + (1 - damping) * restart
        change = np.abs(next_scores - scores).sum(axis=0).max()
        scores = next_scores
        if change < tolerance:
            break
    return scores


def _best_others(
    scores: np.ndarray, source: int, artist_ids: list[int], how_many: int
) -> list[tuple[int, float]]:
    scores = scores.copy()
    scores[source] = 0.0
    candidates = np.flatnonzero(scores > 0)
    if len(candidates) > how_many:
        candidates = candidates[np.argpartition(scores[candidates], -how_many)[-how_many:]]
    ranked = sorted(candidates, key=lambda index: (-scores[index], artist_ids[index]))
    return [(artist_ids[index], float(scores[index])) for index in ranked]
