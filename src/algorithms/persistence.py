"""
JSONL persistence for a single playlist-build run — the data the DNA
visualization will replay.

One file per run at runs/{run_id}.jsonl, one JSON object per line, each
tagged with a "stage" field: seed, candidate, threshold_step, sa_iteration,
tsp_walk, tsp_generation, final.

Captures, per stage:
  - seed: written once, the track the run started from.
  - candidate: the full candidate pool considered, whether selected or not.
  - threshold_step: one line per Jaccard threshold tried while relaxing to
    find enough candidates. Written for both greedy and SA (each has its
    own threshold-relaxation loop), and for both the main selection attempt
    and the discography fallback re-run, if it happens.
  - sa_iteration: one line per SimulatedAnnealer iteration. Only present
    when strategy="sa" — greedy selection has no iteration trace to write.
  - tsp_walk: one line per distinct track ordering TSPOptimizer ever produces,
    written the first time it's seen. Full population every generation is
    affordable because of this cache — see TSPOptimizer's docstring.
  - tsp_generation: one line per TSPOptimizer generation, the full population
    (every member), each referencing a tsp_walk by walk_id rather than
    repeating its track ids.
  - final: the ordered playlist the run produced.
"""

from pathlib import Path

from pydantic import BaseModel

from src.algorithms.models import (
    CandidateTraceEvent,
    FinalTraceEvent,
    SAIterationEvent,
    SeedTraceEvent,
    ThresholdStepEvent,
    TSPGenerationEvent,
    TSPWalkEvent,
)


class RunTraceWriter:
    """Appends one JSONL line per event to runs/{run_id}.jsonl."""

    def __init__(self, run_id: str, runs_dir: Path | str = "runs") -> None:
        self.run_id = run_id
        self._dir = Path(runs_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.path = self._dir / f"{run_id}.jsonl"

    def _write_line(self, event: BaseModel) -> None:
        with self.path.open("a") as f:
            f.write(event.model_dump_json() + "\n")

    def write_seed(self, track_id: str, genres: list[str], release_year: int) -> None:
        self._write_line(SeedTraceEvent(track_id=track_id, genres=sorted(genres), release_year=release_year))

    def write_candidates(self, candidate_tracks: dict[str, dict], candidate_features: list[list]) -> None:
        for track_id, feat in candidate_features:
            track = candidate_tracks.get(track_id, {})
            artists = track.get("artists", [])
            artist = artists[0] if artists else {}
            self._write_line(
                CandidateTraceEvent(
                    track_id=track_id,
                    name=track.get("name", ""),
                    artist_name=artist.get("name", "Unknown"),
                    artist_id=artist.get("id"),
                    genres=sorted(feat.get("genres", set())),
                    release_year=feat.get("release_year", 0),
                )
            )

    def write_threshold_step(self, event: ThresholdStepEvent) -> None:
        self._write_line(event)

    def write_sa_iteration(self, event: SAIterationEvent) -> None:
        self._write_line(event)

    def write_tsp_walk(self, event: TSPWalkEvent) -> None:
        self._write_line(event)

    def write_tsp_generation(self, event: TSPGenerationEvent) -> None:
        self._write_line(event)

    def write_final(self, track_ids: list[str], tsp_score: float, initial_score: float) -> None:
        improvement_pct = round((1 - tsp_score / initial_score) * 100, 1) if initial_score else 0.0
        self._write_line(
            FinalTraceEvent(
                track_ids=track_ids,
                tsp_score=round(tsp_score, 4),
                initial_score=round(initial_score, 4),
                improvement_pct=improvement_pct,
            )
        )


def read_run_trace(run_id: str, runs_dir: Path | str = "runs") -> str:
    """
    Read the raw JSONL content a RunTraceWriter wrote for run_id.

    Returns the file verbatim (one JSON object per line) rather than parsing
    it into a Python list, matching the on-disk format 1:1 — useful if a
    future version streams lines while a run is still in progress instead of
    only serving completed runs.

    Raises FileNotFoundError if no trace exists for run_id. Raises ValueError
    if run_id would resolve outside runs_dir (defensive against path
    traversal, since run_id is caller-supplied and becomes part of a file path).
    """
    base = Path(runs_dir).resolve()
    path = (base / f"{run_id}.jsonl").resolve()
    if path.parent != base:
        raise ValueError(f"Invalid run_id: {run_id!r}")
    if not path.exists():
        raise FileNotFoundError(f"No run trace for run_id={run_id!r}")
    return path.read_text()
