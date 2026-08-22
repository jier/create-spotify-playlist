import pytest

from src.algorithms.models import DistanceWeights, TSPGenerationEvent, TSPWalkEvent
from src.algorithms.tsp import TSPOptimizer, order_by_tsp


@pytest.mark.parametrize("track_count", [6, 2], ids=["six_tracks", "two_tracks"])
def test_order_by_tsp_returns_every_track_reordered_not_dropped_or_duplicated(rock_track_features, track_count):
    track_features = rock_track_features(track_count)

    ordered_ids, final_score, initial_score = order_by_tsp(
        track_features, DistanceWeights(), population_size=8, generations=5
    )

    assert set(ordered_ids) == {f"track_{i}" for i in range(track_count)}
    assert len(ordered_ids) == track_count
    assert isinstance(final_score, float)
    assert isinstance(initial_score, float)
    assert final_score >= 0
    assert initial_score >= 0


def test_order_by_tsp_zero_score_when_all_tracks_are_identical(rock_track_features):
    identical_features = rock_track_features(4, distinct_years=False)

    ordered_ids, final_score, initial_score = order_by_tsp(
        identical_features, DistanceWeights(), population_size=4, generations=3
    )

    assert set(ordered_ids) == {f"track_{i}" for i in range(4)}
    assert final_score == 0.0
    assert initial_score == 0.0


# ---------------------------------------------------------------------------
# TSPOptimizer — generator trace, content-addressed walk cache
# ---------------------------------------------------------------------------


def _walk_events(trace: list) -> list[TSPWalkEvent]:
    return [e for e in trace if isinstance(e, TSPWalkEvent)]


def _generation_events(trace: list) -> list[TSPGenerationEvent]:
    return [e for e in trace if isinstance(e, TSPGenerationEvent)]


def test_run_yields_one_generation_event_per_generation_plus_the_initial_population(rock_track_features):
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=5)

    trace = list(optimizer.run())

    generations = _generation_events(trace)
    # generation 0 = initial random population, 1..5 = evolved -> 6 total
    assert [g.generation for g in generations] == [0, 1, 2, 3, 4, 5]


def test_every_generation_event_carries_the_full_population_untruncated(rock_track_features):
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=5)

    trace = list(optimizer.run())

    for generation in _generation_events(trace):
        assert len(generation.members) == 8


def test_walk_events_are_deduplicated_by_content_not_written_twice(rock_track_features):
    """A survivor walk that reappears in a later generation (same track order,
    same walk_id by construction) must not be written as a second TSPWalkEvent."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=10)

    trace = list(optimizer.run())

    walks = _walk_events(trace)
    walk_ids = [w.walk_id for w in walks]
    assert len(walk_ids) == len(set(walk_ids)), "the same walk_id was written more than once"
    # every walk_id is unique in content too — no two distinct walk_ids share the same ordering
    contents = [tuple(w.track_ids) for w in walks]
    assert len(contents) == len(set(contents)), "two different walk_ids were assigned the same track ordering"


def test_every_population_member_references_a_walk_id_already_written(rock_track_features):
    """Every TSPPopulationMember.walk_id must resolve to a TSPWalkEvent that
    appears at or before it in the trace — a member can never reference a
    walk the reader hasn't seen yet."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=10)

    known_walk_ids: set[int] = set()
    for event in optimizer.run():
        if isinstance(event, TSPWalkEvent):
            known_walk_ids.add(event.walk_id)
        else:
            for member in event.members:
                assert member.walk_id in known_walk_ids


def test_run_to_completion_bundles_walk_and_generation_events_with_final_result(rock_track_features):
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=5)

    ordered_ids, final_score, initial_score, trace = optimizer.run_to_completion()

    assert set(ordered_ids) == {f"track_{i}" for i in range(6)}
    assert isinstance(final_score, float)
    assert isinstance(initial_score, float)
    assert len(_generation_events(trace)) == 6
    assert len(_walk_events(trace)) >= 1
