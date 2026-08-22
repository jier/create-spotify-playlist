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


class ThresholdStepEvent(BaseModel):
    """One Jaccard-distance threshold tried while relaxing to find enough candidates.

    Emitted by both select_greedy and SimulatedAnnealer.__init__, which each
    loop over the same [max_candidate_distance, 0.85, 0.95, 1.0] progression.
    """

    stage: str = "threshold_step"
    threshold: float
    candidates_passing: int
    accepted: bool


class TSPWalkEvent(BaseModel):
    """One distinct track ordering, written the first time it's ever seen in a run.

    walk_id is assigned incrementally by TSPOptimizer as new orderings appear,
    starting from the initial random population (generation 0). Content-addressed
    cache: _apply_selection carries survivors forward unchanged and
    _apply_mutation leaves ~half the population untouched each generation, so
    the same ordering commonly reappears across many generations. This is
    written once per distinct ordering for the whole run, not once per
    (generation, population slot) — that's what keeps a full, untruncated
    population trace affordable.
    """

    stage: str = "tsp_walk"
    walk_id: int
    track_ids: list[str]


class TSPPopulationMember(BaseModel):
    """One population slot in one generation: a reference to a TSPWalkEvent by
    walk_id plus that walk's score in this generation's graph. Not the track
    ids themselves — those are cached once in TSPWalkEvent."""

    walk_id: int
    score: float


class TSPGenerationEvent(BaseModel):
    """One full generation's population: every member, unrounded, unsampled.

    Cheap despite being the full population every generation (no 80% cutoff,
    no aggregate-only summary) because members reference walk_ids rather than
    repeating track ids — the expensive payload lives in TSPWalkEvent, written
    once per distinct ordering, not once per generation.

    generation 0 is the initial random population, before any evolution;
    generations 1..N are each one selection -> crossover -> mutation cycle.
    """

    stage: str = "tsp_generation"
    generation: int
    members: list[TSPPopulationMember]
