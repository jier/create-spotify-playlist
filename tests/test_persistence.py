import json

import pytest

from src.algorithms.models import (
    SAIterationEvent,
    ThresholdStepEvent,
    TSPGenerationEvent,
    TSPPopulationMember,
    TSPWalkEvent,
)
from src.algorithms.persistence import RunTraceWriter, read_run_trace


def _read_lines(writer: RunTraceWriter) -> list[dict]:
    return [json.loads(line) for line in writer.path.read_text().splitlines()]


def test_init_creates_runs_dir_but_not_the_file_yet(tmp_path):
    runs_dir = tmp_path / "runs"
    writer = RunTraceWriter("run_1", runs_dir=runs_dir)

    assert runs_dir.is_dir()
    assert writer.path == runs_dir / "run_1.jsonl"
    assert not writer.path.exists()


def test_write_seed_writes_one_line_with_stage_and_sorted_genres(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)

    writer.write_seed("seed_track", ["rock", "blues"], 1998)

    lines = _read_lines(writer)
    assert lines == [{"stage": "seed", "track_id": "seed_track", "genres": ["blues", "rock"], "release_year": 1998}]


def test_write_candidates_writes_one_line_per_candidate(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    candidate_tracks = {
        "t1": {"name": "Song A", "artists": [{"id": "a1", "name": "Artist A"}]},
        "t2": {"name": "Song B", "artists": [{"id": "a2", "name": "Artist B"}]},
    }
    candidate_features = [
        ["t1", {"genres": {"rock"}, "release_year": 2001}],
        ["t2", {"genres": {"blues", "rock"}, "release_year": 1999}],
    ]

    writer.write_candidates(candidate_tracks, candidate_features)

    lines = _read_lines(writer)
    assert len(lines) == 2
    assert all(line["stage"] == "candidate" for line in lines)
    by_id = {line["track_id"]: line for line in lines}
    assert by_id["t1"] == {
        "stage": "candidate",
        "track_id": "t1",
        "name": "Song A",
        "artist_name": "Artist A",
        "artist_id": "a1",
        "genres": ["rock"],
        "release_year": 2001,
    }
    assert by_id["t2"]["genres"] == ["blues", "rock"]


def test_write_candidates_handles_track_missing_from_candidate_tracks(tmp_path):
    """A candidate feature with no matching entry in candidate_tracks (shouldn't
    happen in practice, but write_candidates must not blow up if it does)."""
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)

    writer.write_candidates({}, [["ghost", {"genres": {"rock"}, "release_year": 2000}]])

    lines = _read_lines(writer)
    assert lines == [
        {
            "stage": "candidate",
            "track_id": "ghost",
            "name": "",
            "artist_name": "Unknown",
            "artist_id": None,
            "genres": ["rock"],
            "release_year": 2000,
        }
    ]


def test_write_sa_iteration_writes_the_event_with_stage(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    event = SAIterationEvent(
        iteration=3,
        temperature=0.5,
        energy=0.12,
        accepted=True,
        out_track_id="out_1",
        in_track_id="in_1",
    )

    writer.write_sa_iteration(event)

    lines = _read_lines(writer)
    assert lines == [
        {
            "stage": "sa_iteration",
            "iteration": 3,
            "temperature": 0.5,
            "energy": 0.12,
            "accepted": True,
            "out_track_id": "out_1",
            "in_track_id": "in_1",
        }
    ]


def test_write_threshold_step_writes_the_event_with_stage(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    event = ThresholdStepEvent(threshold=0.85, candidates_passing=7, accepted=True)

    writer.write_threshold_step(event)

    lines = _read_lines(writer)
    assert lines == [{"stage": "threshold_step", "threshold": 0.85, "candidates_passing": 7, "accepted": True}]


def test_write_tsp_walk_writes_the_event_with_stage(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    event = TSPWalkEvent(walk_id=3, track_ids=["t1", "t2", "t3"])

    writer.write_tsp_walk(event)

    lines = _read_lines(writer)
    assert lines == [{"stage": "tsp_walk", "walk_id": 3, "track_ids": ["t1", "t2", "t3"]}]


def test_write_tsp_generation_writes_the_full_population_nested(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    event = TSPGenerationEvent(
        generation=2,
        members=[TSPPopulationMember(walk_id=0, score=1.5), TSPPopulationMember(walk_id=1, score=2.5)],
    )

    writer.write_tsp_generation(event)

    lines = _read_lines(writer)
    assert lines == [
        {
            "stage": "tsp_generation",
            "generation": 2,
            "members": [{"walk_id": 0, "score": 1.5}, {"walk_id": 1, "score": 2.5}],
        }
    ]


def test_write_final_computes_improvement_pct(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)

    writer.write_final(["a", "b", "c"], tsp_score=5.0, initial_score=10.0)

    lines = _read_lines(writer)
    assert lines == [
        {
            "stage": "final",
            "track_ids": ["a", "b", "c"],
            "tsp_score": 5.0,
            "initial_score": 10.0,
            "improvement_pct": 50.0,
        }
    ]


def test_write_final_guards_against_zero_initial_score(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)

    writer.write_final(["a"], tsp_score=0.0, initial_score=0.0)

    lines = _read_lines(writer)
    assert lines[0]["improvement_pct"] == 0.0


def test_writes_append_in_call_order(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)

    writer.write_seed("seed", ["rock"], 2000)
    writer.write_candidates({}, [["t1", {"genres": {"rock"}, "release_year": 2000}]])
    writer.write_final(["seed", "t1"], tsp_score=1.0, initial_score=2.0)

    stages = [line["stage"] for line in _read_lines(writer)]
    assert stages == ["seed", "candidate", "final"]


def test_two_writers_with_different_run_ids_produce_separate_files(tmp_path):
    writer_a = RunTraceWriter("run_a", runs_dir=tmp_path)
    writer_b = RunTraceWriter("run_b", runs_dir=tmp_path)

    writer_a.write_seed("seed_a", ["rock"], 2000)
    writer_b.write_seed("seed_b", ["blues"], 1990)

    assert _read_lines(writer_a) == [{"stage": "seed", "track_id": "seed_a", "genres": ["rock"], "release_year": 2000}]
    assert _read_lines(writer_b) == [{"stage": "seed", "track_id": "seed_b", "genres": ["blues"], "release_year": 1990}]


# ---------------------------------------------------------------------------
# read_run_trace
# ---------------------------------------------------------------------------


def test_read_run_trace_returns_file_content_verbatim(tmp_path):
    writer = RunTraceWriter("run_1", runs_dir=tmp_path)
    writer.write_seed("seed", ["rock"], 2000)
    writer.write_final(["seed"], tsp_score=0.0, initial_score=0.0)

    content = read_run_trace("run_1", runs_dir=tmp_path)

    assert content == writer.path.read_text()
    assert [json.loads(line)["stage"] for line in content.splitlines()] == ["seed", "final"]


def test_read_run_trace_raises_file_not_found_for_missing_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_run_trace("does_not_exist", runs_dir=tmp_path)


@pytest.mark.parametrize("malicious_run_id", ["../secret", "../../etc/passwd", "sub/dir"])
def test_read_run_trace_rejects_run_id_that_would_escape_runs_dir(tmp_path, malicious_run_id):
    with pytest.raises(ValueError):
        read_run_trace(malicious_run_id, runs_dir=tmp_path)
