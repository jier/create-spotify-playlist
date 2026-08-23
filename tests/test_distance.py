import pytest

from src.algorithms.distance import get_distance, jaccard_distance
from src.algorithms.models import DistanceWeights


@pytest.mark.parametrize(
    ("genres_a", "genres_b", "expected"),
    [
        ({"rock"}, {"rock"}, 0.0),
        ({"rock"}, {"pop"}, 1.0),
        ({"rock", "pop"}, {"pop", "jazz"}, 1.0 - 1 / 3),
        (set(), set(), 1.0),
    ],
    ids=["identical", "disjoint", "partial_overlap", "both_empty"],
)
def test_jaccard_distance(genres_a, genres_b, expected):
    assert jaccard_distance(genres_a, genres_b) == expected


@pytest.mark.parametrize(
    ("weights", "genres_a", "genres_b", "year_a", "year_b", "expected"),
    [
        (
            DistanceWeights(genre_weight=1.0, year_weight=0.5),
            {"rock"},
            {"pop"},
            2000,
            2010,
            1.0 * 1.0 + 0.5 * 0.2,
        ),
        (
            DistanceWeights(genre_weight=0.0, year_weight=1.0),
            {"rock"},
            {"rock"},
            1970,
            2020,
            1.0,
        ),
    ],
    ids=["combines_genre_and_year_with_weights", "caps_year_distance_at_one"],
)
def test_get_distance(weights, genres_a, genres_b, year_a, year_b, expected):
    track_a = ["a", {"genres": genres_a, "release_year": year_a}]
    track_b = ["b", {"genres": genres_b, "release_year": year_b}]

    assert get_distance(track_a, track_b, weights) == expected
