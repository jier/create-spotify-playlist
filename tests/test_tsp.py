from collections.abc import Iterable

import pytest

from src.algorithms.models import DistanceWeights, TSPGenerationEvent, TSPWalkEvent
from src.algorithms.tsp import TSPOptimizer, TSPTraceEvent, Walk, order_by_tsp


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


def _walk_events(trace: Iterable[TSPTraceEvent]) -> list[TSPWalkEvent]:
    return [e for e in trace if isinstance(e, TSPWalkEvent)]


def _generation_events(trace: Iterable[TSPTraceEvent]) -> list[TSPGenerationEvent]:
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


def test_optimizer_returns_best_walk_seen_not_only_last_generation(rock_track_features, monkeypatch):
    optimizer = TSPOptimizer(rock_track_features(6), DistanceWeights(), population_size=8, generations=1)
    initial_best_score = optimizer.initial_score

    def make_every_walk_worse(population, _graph, _register):
        return [
            Walk(
                track_ids=walk.track_ids,
                score=walk.score + 10,
                walk_id=walk.walk_id,
                parent_walk_ids=walk.parent_walk_ids,
            )
            for walk in population
        ]

    monkeypatch.setattr("src.algorithms.tsp._apply_genetics", make_every_walk_worse)

    _, final_score, _, trace = optimizer.run_to_completion()

    last_generation = _generation_events(trace)[-1]
    assert min(member.score for member in last_generation.members) > initial_best_score
    assert final_score == initial_best_score


# ---------------------------------------------------------------------------
# TSPOptimizer — walk lineage (parent_walk_ids)
# ---------------------------------------------------------------------------


def test_initial_population_walks_have_no_parents(rock_track_features):
    """generation 0's random population has no lineage — nothing produced it."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=0)

    trace = list(optimizer.run())

    walks = _walk_events(trace)
    # Eight population slots do not guarantee eight distinct orderings:
    # random shuffles can collide and the content-addressed registry emits a
    # TSPWalkEvent only once per distinct ordering. The separate population
    # test above verifies all eight slots are still present.
    assert 1 <= len(walks) <= 8
    assert all(w.parent_walk_ids == [] for w in walks)


def test_every_walk_parent_id_was_already_registered_before_it(rock_track_features):
    """A walk_id can only ever be referenced as a parent after its own
    TSPWalkEvent has already appeared — parents must precede children,
    exactly like a DAG (or git commit parents)."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=15)

    known_walk_ids: set[int] = set()
    for walk in _walk_events(optimizer.run()):
        for parent_id in walk.parent_walk_ids:
            assert parent_id in known_walk_ids, f"walk {walk.walk_id} references parent {parent_id} before it exists"
        known_walk_ids.add(walk.walk_id)


def test_every_walk_has_zero_one_or_two_parents(rock_track_features):
    """0 = random init, 1 = mutation (single-parent rotation), 2 = crossover.
    Never anything else, structurally, regardless of how many generations run."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=15)

    for walk in _walk_events(optimizer.run()):
        assert len(walk.parent_walk_ids) in (0, 1, 2)


def test_crossover_produces_two_parent_walks_and_mutation_produces_one_parent_walks(rock_track_features):
    """Over enough generations, both lineage shapes must actually occur —
    this is what proves crossover and mutation are both really wired into
    register(), not just structurally possible but never exercised."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=15)

    parent_counts = {len(w.parent_walk_ids) for w in _walk_events(optimizer.run())}

    assert 2 in parent_counts, "no crossover-produced (two-parent) walk ever appeared"
    assert 1 in parent_counts, "no mutation-produced (one-parent) walk ever appeared"


def test_a_walk_carried_forward_by_mutation_can_have_a_same_generation_crossover_child_as_its_parent(
    rock_track_features,
):
    """The hard case: a crossover child gets mutated in the very same
    _apply_genetics() call, before TSPOptimizer ever gets a chance to process
    a generation boundary. The mutated walk's parent must still resolve to
    that same-generation crossover child (a two-parent walk itself), proving
    register() resolves ids immediately at creation time rather than only
    after a generation completes."""
    track_features = rock_track_features(6)
    optimizer = TSPOptimizer(track_features, DistanceWeights(), population_size=8, generations=15)

    walks_by_id = {w.walk_id: w for w in _walk_events(optimizer.run())}
    one_parent_walks = [w for w in walks_by_id.values() if len(w.parent_walk_ids) == 1]
    assert any(len(walks_by_id[w.parent_walk_ids[0]].parent_walk_ids) == 2 for w in one_parent_walks), (
        "no mutation ever had a same-run crossover child as its parent"
    )
