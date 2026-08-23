import pytest

from src.algorithms.models import (
    DistanceWeights,
    GreedySelectionConfig,
    SAIterationEvent,
    SimulatedAnnealingConfig,
    ThresholdStepEvent,
)
from src.algorithms.selection import SimulatedAnnealer, _energy, select_greedy


def test_select_greedy_enforces_per_artist_cap(rock_seed_feat):
    config = GreedySelectionConfig(max_tracks_per_artist=2, weights=DistanceWeights())

    candidate_features = [[f"artist_a_track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(4)] + [
        ["artist_b_track_0", {"genres": {"rock"}, "release_year": 2000}]
    ]
    candidate_tracks = {
        **{f"artist_a_track_{i}": {"artists": [{"id": "artist_a"}]} for i in range(4)},
        "artist_b_track_0": {"artists": [{"id": "artist_b"}]},
    }

    top_n, fallback, threshold_used, threshold_trace = select_greedy(
        candidate_features, rock_seed_feat, candidate_tracks, n=3, config=config
    )

    assert len(top_n) == 3
    artist_a_count = sum(1 for tid, _ in top_n if tid.startswith("artist_a"))
    assert artist_a_count <= 2
    assert fallback == "genre_search"
    assert threshold_used == 0.75
    assert threshold_trace == [ThresholdStepEvent(threshold=0.75, candidates_passing=5, accepted=True)]


def test_select_greedy_relaxes_threshold_when_seed_genre_has_no_close_match():
    config = GreedySelectionConfig()

    seed_feat = ["seed", {"genres": {"metal"}, "release_year": 2000}]
    candidate_features = [["off_genre_track", {"genres": {"jazz"}, "release_year": 2000}]]
    candidate_tracks = {"off_genre_track": {"artists": [{"id": "artist_x"}]}}

    top_n, fallback, threshold_used, threshold_trace = select_greedy(
        candidate_features, seed_feat, candidate_tracks, n=1, config=config
    )

    assert len(top_n) == 1
    assert threshold_used == 1.0
    assert fallback == "relaxed_threshold_1.0"
    # jazz vs metal never passes the Jaccard threshold until it's fully relaxed to 1.0 —
    # one rejected step per threshold tried before the final accepted one.
    assert [step.threshold for step in threshold_trace] == [0.75, 0.85, 0.95, 1.0]
    assert [step.accepted for step in threshold_trace] == [False, False, False, True]
    assert [step.candidates_passing for step in threshold_trace] == [0, 0, 0, 1]


def test_select_greedy_rejects_non_positive_track_count(rock_seed_feat):
    with pytest.raises(ValueError, match="n must be at least 1"):
        select_greedy([], rock_seed_feat, {}, n=0, config=GreedySelectionConfig())


# ---------------------------------------------------------------------------
# _energy — standalone, no closures, directly testable on its own
# ---------------------------------------------------------------------------


def test_energy_zero_when_selection_is_identical_to_seed_and_to_itself():
    """All selected tracks identical to the seed and to each other: both
    relevance distance and pairwise diversity distance are 0, so energy is 0
    regardless of diversity_weight."""
    pool = [["a", {"genres": {"rock"}, "release_year": 2000}], ["b", {"genres": {"rock"}, "release_year": 2000}]]
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]

    result = _energy([0, 1], pool, seed_feat, DistanceWeights(), diversity_weight=0.5, n=2)

    assert result == 0.0


def test_energy_equals_avg_relevance_when_diversity_weight_is_zero():
    """With diversity_weight=0, energy is exactly the average distance from the
    seed to each selected track, the diversity term contributes nothing."""
    pool = [["a", {"genres": {"pop"}, "release_year": 2000}], ["b", {"genres": {"pop"}, "release_year": 2000}]]
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    weights = DistanceWeights(genre_weight=1.0, year_weight=0.0)

    result = _energy([0, 1], pool, seed_feat, weights, diversity_weight=0.0, n=2)

    # genre_dist(rock, pop) = 1.0 for both -> avg_relevance = 1.0, diversity term zeroed out
    assert result == 1.0


def test_energy_decreases_as_diversity_weight_increases_for_a_diverse_pair():
    """Same selection, higher diversity_weight should push energy lower when
    the selected pair is genuinely diverse from each other."""
    pool = [["a", {"genres": {"rock"}, "release_year": 2000}], ["b", {"genres": {"pop"}, "release_year": 2000}]]
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]

    low_beta = _energy([0, 1], pool, seed_feat, DistanceWeights(), diversity_weight=0.1, n=2)
    high_beta = _energy([0, 1], pool, seed_feat, DistanceWeights(), diversity_weight=0.9, n=2)

    assert high_beta < low_beta


def test_energy_for_one_track_has_zero_pairwise_diversity():
    pool = [["a", {"genres": {"pop"}, "release_year": 2000}]]
    seed_feat = ["seed", {"genres": {"rock"}, "release_year": 2000}]

    result = _energy([0], pool, seed_feat, DistanceWeights(), diversity_weight=0.5, n=1)

    assert result == 1.0


# ---------------------------------------------------------------------------
# SimulatedAnnealer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pool_size", [3, 5], ids=["pool_smaller_than_n", "pool_equal_to_n"])
def test_simulated_annealer_run_yields_no_events_when_pool_at_or_below_n(
    rock_candidate_pool, rock_seed_feat, pool_size
):
    candidate_features, _ = rock_candidate_pool(pool_size)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=30), candidate_features, rock_seed_feat, n=5)

    events = list(annealer.run())

    assert events == []


@pytest.mark.parametrize("pool_size", [3, 5], ids=["pool_smaller_than_n", "pool_equal_to_n"])
def test_simulated_annealer_run_to_completion_matches_sa_all_candidates_shortcut(
    rock_candidate_pool, rock_seed_feat, pool_size
):
    candidate_features, _ = rock_candidate_pool(pool_size)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=30), candidate_features, rock_seed_feat, n=5)

    top_n, fallback, _, trace, threshold_trace = annealer.run_to_completion()

    assert len(top_n) == pool_size
    assert fallback == "sa_all_candidates"
    assert trace == []
    # pool_size == n (5): the very first threshold already has enough candidates, one step.
    # pool_size < n (3): no threshold ever reaches n candidates (only 3 exist total), all
    # 4 progression steps run and are recorded as not-accepted, the shortcut triggers after.
    if pool_size >= 5:
        assert threshold_trace == [ThresholdStepEvent(threshold=0.75, candidates_passing=pool_size, accepted=True)]
    else:
        assert [step.accepted for step in threshold_trace] == [False, False, False, False]
        assert all(step.candidates_passing == pool_size for step in threshold_trace)


def test_simulated_annealer_run_yields_one_event_per_iteration(rock_candidate_pool, rock_seed_feat):
    candidate_features, _ = rock_candidate_pool(10)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=10), candidate_features, rock_seed_feat, n=4)

    events = list(annealer.run())

    assert len(events) == 10
    assert all(isinstance(e, SAIterationEvent) for e in events)
    assert [e.iteration for e in events] == list(range(10))


def test_simulated_annealer_supports_one_track_selection(rock_candidate_pool, rock_seed_feat):
    candidate_features, _ = rock_candidate_pool(3)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=3), candidate_features, rock_seed_feat, n=1)

    top_n, _, _, trace, _ = annealer.run_to_completion()

    assert len(top_n) == 1
    assert len(trace) == 3


def test_simulated_annealer_rejects_non_positive_track_count(rock_seed_feat):
    with pytest.raises(ValueError, match="n must be at least 1"):
        SimulatedAnnealer(SimulatedAnnealingConfig(), [], rock_seed_feat, n=0)


def test_simulated_annealer_run_to_completion_returns_n_distinct_tracks_and_full_trace(
    rock_candidate_pool, rock_seed_feat
):
    candidate_features, candidate_tracks = rock_candidate_pool(10)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=10), candidate_features, rock_seed_feat, n=4)

    top_n, _, _, trace, _ = annealer.run_to_completion()

    ids = [tid for tid, _ in top_n]
    assert len(ids) == 4
    assert len(set(ids)) == 4
    assert set(ids).issubset(set(candidate_tracks))
    assert len(trace) == 10
    for event in trace:
        assert event.out_track_id in candidate_tracks
        assert event.in_track_id in candidate_tracks


def test_simulated_annealer_trace_events_carry_valid_ids_across_pool(rock_candidate_pool, rock_seed_feat):
    """Every yielded event's out/in track ids must belong to the candidate pool
    actually being annealed over, not some stale or out-of-range index."""
    candidate_features, candidate_tracks = rock_candidate_pool(8)
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=25), candidate_features, rock_seed_feat, n=3)

    for event in annealer.run():
        assert event.out_track_id in candidate_tracks
        assert event.in_track_id in candidate_tracks
        assert isinstance(event.accepted, bool)
        assert event.temperature > 0


def test_rejected_sa_proposal_reports_committed_energy(monkeypatch):
    seed = ["seed", {"genres": {"rock"}, "release_year": 2000}]
    pool = [
        ["a", {"genres": {"rock"}, "release_year": 2000}],
        ["b", {"genres": {"rock"}, "release_year": 2001}],
        ["far", {"genres": {"pop"}, "release_year": 2020}],
    ]
    config = SimulatedAnnealingConfig(iterations=1, max_candidate_distance=1.0)
    monkeypatch.setattr("src.algorithms.selection.random.sample", lambda _population, _n: [0, 1])
    monkeypatch.setattr("src.algorithms.selection.random.randrange", lambda _limit: 0)
    monkeypatch.setattr("src.algorithms.selection.random.random", lambda: 1.0)
    initial_energy = _energy([0, 1], pool, seed, config.weights, config.diversity_weight, n=2)

    _, _, _, trace, _ = SimulatedAnnealer(config, pool, seed, n=2).run_to_completion()

    assert trace[0].accepted is False
    assert trace[0].energy == initial_energy


def test_simulated_annealer_relaxes_threshold_when_seed_genre_has_no_close_match():
    seed_feat = ["seed", {"genres": {"metal"}, "release_year": 2000}]
    candidate_features = [["off_genre_track", {"genres": {"jazz"}, "release_year": 2000}]]
    annealer = SimulatedAnnealer(SimulatedAnnealingConfig(iterations=30), candidate_features, seed_feat, n=1)

    top_n, fallback, threshold_used, trace, threshold_trace = annealer.run_to_completion()

    assert len(top_n) == 1
    assert threshold_used == 1.0
    assert fallback == "sa_all_candidates"
    assert trace == []
    assert [step.threshold for step in threshold_trace] == [0.75, 0.85, 0.95, 1.0]
    assert [step.accepted for step in threshold_trace] == [False, False, False, True]
    assert [step.candidates_passing for step in threshold_trace] == [0, 0, 0, 1]
