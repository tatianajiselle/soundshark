from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneSettings:
    related_per_artist: int = 10
    resolution: float = 1.5
    consensus_runs: int = 10
    consensus_agreement: float = 0.5
    min_scene_size: int = 15
    min_overlap: float = 0.3
    seed: int = 7
