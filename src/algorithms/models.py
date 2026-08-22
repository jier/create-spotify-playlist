"""
Pydantic contracts for the pure playlist-building algorithms.

Everything here is data crossing a boundary: configuration that a future batch
job could load from a file instead of the running app's settings, and trace
events that become one JSONL line each once persistence is wired up. Keeping
them in one file makes it visible at a glance which types in this package are
contracts, versus the plain lists/dicts the algorithms compute with
internally, which don't need this treatment.
"""

from pydantic import BaseModel


class DistanceWeights(BaseModel):
    """How genre and release-year differences combine into one distance value."""

    genre_weight: float = 1.0
    year_weight: float = 0.5


class GreedySelectionConfig(BaseModel):
    """Parameters for select_greedy. No global settings read inside the algorithm itself."""

    max_candidate_distance: float = 0.75
    max_tracks_per_artist: int = 3
    weights: DistanceWeights = DistanceWeights()


class SimulatedAnnealingConfig(BaseModel):
    """Parameters for SimulatedAnnealer. No global settings read inside the algorithm itself."""

    max_candidate_distance: float = 0.75
    diversity_weight: float = 0.5
    temperature_start: float = 1.0
    temperature_end: float = 0.01
    iterations: int = 1000
    weights: DistanceWeights = DistanceWeights()


class SAIterationEvent(BaseModel):
    """One simulated annealing iteration. Written as one JSONL line by RunTraceWriter."""

    stage: str = "sa_iteration"
    iteration: int
    temperature: float
    energy: float
    accepted: bool
    out_track_id: str
    in_track_id: str


class SeedTraceEvent(BaseModel):
    """The seed track a run started from. First line of every run's JSONL file."""

    stage: str = "seed"
    track_id: str
    genres: list[str]
    release_year: int


class CandidateTraceEvent(BaseModel):
    """One candidate considered for the playlist, whether or not it was selected."""

    stage: str = "candidate"
    track_id: str
    name: str
    artist_name: str
    artist_id: str | None
    genres: list[str]
    release_year: int


class FinalTraceEvent(BaseModel):
    """The final ordered playlist a run produced. Last line of every run's JSONL file."""

    stage: str = "final"
    track_ids: list[str]
    tsp_score: float
    initial_score: float
    improvement_pct: float
