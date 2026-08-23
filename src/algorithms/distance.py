"""
Distance functions. Pure: no HTTP, no global settings, everything explicit.

Spotify deprecated /audio-features in November 2024 — 403 for new apps.
Distance uses two remaining signals:
  1. Genre Jaccard distance  = 1 - (|genres_A ∩ genres_B| / |genres_A ∪ genres_B|)
  2. Release year distance   = min(|year_A - year_B| / 50, 1.0)  (normalized over 50-year span)
"""

from src.algorithms.models import DistanceWeights


def jaccard_distance(genres_a: set[str], genres_b: set[str]) -> float:
    union = genres_a | genres_b
    if not union:
        return 1.0
    return 1.0 - len(genres_a & genres_b) / len(union)


def get_distance(a: list, b: list, weights: DistanceWeights) -> float:
    genre_dist = jaccard_distance(a[1].get("genres", set()), b[1].get("genres", set()))
    year_dist = min(abs(a[1].get("release_year", 0) - b[1].get("release_year", 0)) / 50.0, 1.0)
    return weights.genre_weight * genre_dist + weights.year_weight * year_dist
