from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphScoring:
    b2b_weight: float = 3.0
    same_room_weight: float = 2.0
    same_night_weight: float = 1.0
    recency_half_life_years: float = 3.0
    pagerank_damping: float = 0.85
    related_per_artist: int = 50
