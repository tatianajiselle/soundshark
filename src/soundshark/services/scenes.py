from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import networkx as nx

from soundshark.models.scene_settings import SceneSettings

RankedRelated = Mapping[int, Sequence[tuple[int, float]]]
LABEL_MEMBERS = 3
leiden_communities = cast(Callable[..., Iterable[set[Any]]], nx.community.leiden_communities)


@dataclass(frozen=True, slots=True)
class Scene:
    id: int
    label: str
    members: frozenset[int]


def related_graph(ranked: RankedRelated, top: int) -> nx.Graph:
    weights: dict[tuple[int, int], float] = defaultdict(float)
    artist_ids: set[int] = set()
    for artist_id, others in ranked.items():
        artist_ids.add(artist_id)
        kept = [(other_id, score) for other_id, score in others[:top] if other_id != artist_id and score > 0]
        total = sum(score for _, score in kept)
        for other_id, score in kept:
            artist_ids.add(other_id)
            weights[min(artist_id, other_id), max(artist_id, other_id)] += score / total
    graph = nx.Graph()
    graph.add_nodes_from(sorted(artist_ids))
    graph.add_weighted_edges_from((a_id, b_id, weight) for (a_id, b_id), weight in sorted(weights.items()))
    return graph


def consensus_graph(graph: nx.Graph, resolution: float, seed: int, runs: int, agreement: float) -> nx.Graph:
    community_of: list[dict[int, int]] = []
    for run in range(runs):
        communities = nx.community.louvain_communities(
            graph, weight="weight", resolution=resolution, seed=seed + run
        )
        community_of.append({node: index for index, members in enumerate(communities) for node in members})
    consensus = nx.Graph()
    consensus.add_nodes_from(graph.nodes)
    for a_id, b_id, weight in graph.edges(data="weight"):
        together = sum(1 for labels in community_of if labels[a_id] == labels[b_id]) / runs
        if together >= agreement:
            consensus.add_edge(a_id, b_id, weight=weight * together)
    return consensus


def find_communities(graph: nx.Graph, settings: SceneSettings) -> list[frozenset[int]]:
    if graph.number_of_edges() > 0 and settings.consensus_runs > 1:
        graph = consensus_graph(
            graph, settings.resolution, settings.seed, settings.consensus_runs, settings.consensus_agreement
        )
    if graph.number_of_edges() == 0:
        communities = [{node} for node in graph.nodes]
    else:
        communities = leiden_communities(
            graph, weight="weight", resolution=settings.resolution, seed=settings.seed, metric="modularity"
        )
    return sorted((frozenset(c) for c in communities), key=lambda c: (-len(c), min(c)))


def match_scene_ids(
    communities: Sequence[frozenset[int]], previous: Mapping[int, frozenset[int]], min_overlap: float
) -> list[int]:
    previous_scene_of = {
        artist_id: scene_id for scene_id, members in previous.items() for artist_id in members
    }
    candidates: list[tuple[int, float, int, int]] = []
    for index, members in enumerate(communities):
        shared_with = Counter(previous_scene_of[a] for a in members if a in previous_scene_of)
        for scene_id, shared in shared_with.items():
            jaccard = shared / len(members | previous[scene_id])
            if jaccard >= min_overlap:
                candidates.append((-shared, -jaccard, scene_id, index))
    ids: list[int | None] = [None] * len(communities)
    taken: set[int] = set()
    for _, _, scene_id, index in sorted(candidates):
        if ids[index] is None and scene_id not in taken:
            ids[index] = scene_id
            taken.add(scene_id)
    next_id = max(previous, default=0) + 1
    assigned: list[int] = []
    for scene_id in ids:
        if scene_id is None:
            scene_id = next_id
            next_id += 1
        assigned.append(scene_id)
    return assigned


def scene_label(members: frozenset[int], nights: Mapping[int, int], names: Mapping[int, str]) -> str:
    def name(artist_id: int) -> str:
        return names.get(artist_id, str(artist_id))

    busiest = sorted(members, key=lambda a: (-nights.get(a, 0), name(a).casefold(), name(a), a))[
        :LABEL_MEMBERS
    ]
    return " / ".join(name(a) for a in busiest)


def detect_scenes(
    ranked: RankedRelated,
    previous: Mapping[int, frozenset[int]],
    nights: Mapping[int, int],
    names: Mapping[int, str],
    settings: SceneSettings,
) -> list[Scene]:
    graph = related_graph(ranked, settings.related_per_artist)
    communities = [
        members for members in find_communities(graph, settings) if len(members) >= settings.min_scene_size
    ]
    ids = match_scene_ids(communities, previous, settings.min_overlap)
    return [
        Scene(scene_id, scene_label(members, nights, names), members)
        for scene_id, members in zip(ids, communities, strict=True)
    ]
