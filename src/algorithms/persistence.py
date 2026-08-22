"""
JSONL persistence for a single playlist-build run — the data the DNA
visualization will replay.

One file per run at runs/{run_id}.jsonl, one JSON object per line, each
tagged with a "stage" field: seed, candidate, sa_iteration, final.

Honest scope of what this currently captures, so it isn't oversold:
  - seed: written once, the track the run started from.
  - candidate: the full candidate pool considered, whether selected or not.
  - sa_iteration: one line per SimulatedAnnealer iteration. Only present
    when strategy="sa" — greedy selection has no iteration trace to write.
  - final: the ordered playlist the run produced.

Not yet captured (real gaps, not silently skipped):
  - threshold relaxation steps inside select_greedy / the discography
    fallback path — those decisions aren't emitted as events yet.
  - per-generation TSP trace — order_by_tsp returns only
    (ordered_ids, final_score, initial_score), it doesn't yield
    intermediate generations, so there is nothing to write per-generation
    yet. Would need order_by_tsp turned into a generator, mirroring what
    SimulatedAnnealer.run() already does.
"""

from pathlib import Path

from pydantic import BaseModel

from src.algorithms.models import CandidateTraceEvent, FinalTraceEvent, SAIterationEvent, SeedTraceEvent


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

    def write_sa_iteration(self, event: SAIterationEvent) -> None:
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
