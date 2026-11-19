from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphScoring:
    b2b_weight: float = 4.0
    same_room_weight: float = 3.0
    same_night_weight: float = 0.25
    room_profile_floor: float = 0.25
    recency_half_life_years: float = 3.0
    night_count_padding: float = 40.0
    pagerank_damping: float = 0.95
    related_per_artist: int = 50
