import math
import random
from collections.abc import Callable, Mapping, Sequence

import igraph as ig

LAYOUT_LINKS_PER_ARTIST = 3
MAIN_COMPONENT_SHARE = 0.02
LAYOUT_ITERATIONS = 500
LAYOUT_RADIUS = 400.0
LAYOUT_SEED = 0

type Position = list[float]
type RankedRow = tuple[int, int, int, float]
type Layout = Callable[[Sequence[int], Sequence[RankedRow]], Mapping[int, Position]]


def main_artists(artist_ids: Sequence[int], related: Sequence[RankedRow]) -> list[int]:
    index = {artist_id: i for i, artist_id in enumerate(artist_ids)}
    graph = ig.Graph(n=len(artist_ids), edges=_pairs(index, related, None))
    components = list(graph.connected_components())
    if not components:
        return []
    largest = max(len(component) for component in components)
    threshold = min(largest, max(3, math.ceil(len(artist_ids) * MAIN_COMPONENT_SHARE)))
    kept = sorted(i for component in components if len(component) >= threshold for i in component)
    return [artist_ids[i] for i in kept]


def layout_3d(artist_ids: Sequence[int], related: Sequence[RankedRow]) -> dict[int, Position]:
    shown = main_artists(artist_ids, related)
    if not shown:
        return {}
    index = {artist_id: i for i, artist_id in enumerate(shown)}
    graph = ig.Graph(n=len(shown), edges=_pairs(index, related, LAYOUT_LINKS_PER_ARTIST))
    ig.set_random_number_generator(random.Random(LAYOUT_SEED))
    try:
        layout = graph.layout_fruchterman_reingold(dim=3, niter=LAYOUT_ITERATIONS, grid=len(shown) > 1000)
        coords = layout.coords
    finally:
        ig.set_random_number_generator(random)
    return dict(zip(shown, _normalized(coords), strict=True))


def _pairs(
    index: dict[int, int], related: Sequence[RankedRow], max_rank: int | None
) -> list[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for artist_id, rank, other_id, _ in related:
        if max_rank is not None and rank > max_rank:
            continue
        a, b = index.get(artist_id), index.get(other_id)
        if a is None or b is None or a == b:
            continue
        pairs.add((min(a, b), max(a, b)))
    return sorted(pairs)


def _normalized(coords: Sequence[Sequence[float]]) -> list[Position]:
    count = len(coords)
    centre = [sum(point[axis] for point in coords) / count for axis in range(3)]
    shifted = [[point[axis] - centre[axis] for axis in range(3)] for point in coords]
    spread = math.sqrt(sum(x * x + y * y + z * z for x, y, z in shifted) / count) or 1.0
    scale = LAYOUT_RADIUS / spread
    return [[round(value * scale, 1) for value in point] for point in shifted]
