import pytest

from src.algorithms.models import DistanceWeights
from src.algorithms.tsp import order_by_tsp


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
