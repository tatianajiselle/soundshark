from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RankingChange:
    artist_id: int
    name: str
    nights: int
    change: float
    entered: list[str]
    left: list[str]


def list_change(before: Sequence[int], after: Sequence[int]) -> float:
    before_set, after_set = set(before), set(after)
    union = before_set | after_set
    if not union:
        return 0.0
    return 1 - len(before_set & after_set) / len(union)


def ranking_changes(
    before: Mapping[int, Sequence[int]],
    after: Mapping[int, Sequence[int]],
    nights: Mapping[int, int],
    names: Mapping[int, str],
    *,
    top: int,
    min_nights: int,
) -> list[RankingChange]:
    def name_of(artist_id: int) -> str:
        return names.get(artist_id, f"#{artist_id}")

    changes: list[RankingChange] = []
    for artist_id, artist_nights in nights.items():
        if artist_nights < min_nights:
            continue
        old_top = list(before.get(artist_id, []))[:top]
        new_top = list(after.get(artist_id, []))[:top]
        changes.append(
            RankingChange(
                artist_id=artist_id,
                name=name_of(artist_id),
                nights=artist_nights,
                change=list_change(old_top, new_top),
                entered=[name_of(other) for other in new_top if other not in old_top],
                left=[name_of(other) for other in old_top if other not in new_top],
            )
        )
    return sorted(changes, key=lambda c: (-c.change, -c.nights, c.name, c.artist_id))
