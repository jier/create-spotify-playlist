"""
Pluggable Step 5 selection strategies for build_playlist_from_seed.

Both strategies share the same signature:
    (candidate_features, seed_feat, candidate_tracks, n) -> (top_n, fallback, threshold_used)

Distance functions live here so selectionStrategies is self-contained and playlistBuilderService
imports from it (no circular dependency).
"""

import math
import random

from ..settings import settings

# ---------------------------------------------------------------------------
# Distance functions (moved here from playlistBuilderService)
# ---------------------------------------------------------------------------


def jaccard_distance(genres_a: set[str], genres_b: set[str]) -> float:
    union = genres_a | genres_b
    if not union:
        return 1.0
    return 1.0 - len(genres_a & genres_b) / len(union)


def get_distance(a: list, b: list) -> float:
    genre_dist = jaccard_distance(a[1].get("genres", set()), b[1].get("genres", set()))
    year_dist = min(abs(a[1].get("release_year", 0) - b[1].get("release_year", 0)) / 50.0, 1.0)
    return settings.playlist_genre_weight * genre_dist + settings.playlist_year_weight * year_dist


# ---------------------------------------------------------------------------
# Shared: Jaccard threshold filter
# ---------------------------------------------------------------------------


def _filter_by_threshold(
    candidate_features: list[list],
    seed_genres: set[str],
    threshold: float,
) -> list[list]:
    return [c for c in candidate_features if jaccard_distance(seed_genres, c[1].get("genres", set())) <= threshold]


# ---------------------------------------------------------------------------
# Strategy: greedy artist-capped selection
# ---------------------------------------------------------------------------


def select_greedy(
    candidate_features: list[list],
    seed_feat: list,
    candidate_tracks: dict[str, dict],
    n: int,
) -> tuple[list[list], str, float]:
    """
    Walk candidates in distance order, enforce per-artist cap at selection time.
    Relax Jaccard threshold progressively until n tracks are found.
    Returns (top_n, fallback_label, threshold_used).
    """
    seed_genres = seed_feat[1].get("genres", set())
    fallback = "genre_search"
    threshold_used = settings.playlist_max_candidate_distance
    top_n: list[list] = []

    for threshold in [settings.playlist_max_candidate_distance, 0.85, 0.95, 1.0]:
        genre_relevant = _filter_by_threshold(candidate_features, seed_genres, threshold)
        top_n = []
        artist_counts: dict[str, int] = {}
        for c in sorted(genre_relevant, key=lambda c: get_distance(seed_feat, c)):
            artists = candidate_tracks.get(c[0], {}).get("artists", [])
            aid = artists[0]["id"] if artists else ""
            if artist_counts.get(aid, 0) >= settings.playlist_max_tracks_per_artist:
                continue
            artist_counts[aid] = artist_counts.get(aid, 0) + 1
            top_n.append(c)
            if len(top_n) >= n:
                break
        threshold_used = threshold
        if threshold > settings.playlist_max_candidate_distance:
            fallback = f"relaxed_threshold_{threshold}"
        if len(top_n) >= n:
            break

    return top_n, fallback, threshold_used


# ---------------------------------------------------------------------------
# Strategy: simulated annealing diverse subset selection
# ---------------------------------------------------------------------------


def select_sa(
    candidate_features: list[list],
    seed_feat: list,
    candidate_tracks: dict[str, dict],
    n: int,
) -> tuple[list[list], str, float]:
    """
    Simulated annealing diverse subset selection.

    Energy (minimised):
        E(S) = avg_relevance(S) − sa_diversity_weight × avg_pairwise_diversity(S)
             = mean dist(seed, sᵢ) − β × mean dist(sᵢ, sⱼ) for all pairs

    Normalised so β=1.0 = equal weight on relevance and pairwise spread.
    Accepts worse moves with prob e^(−ΔE/T), T cools from sa_temperature_start to sa_temperature_end.

    Escapes the greedy cap failure mode: greedy cannot undo an early popular-artist pick;
    SA can swap it out later if a more diverse set lowers energy.

    Returns (top_n, fallback_label, threshold_used).
    """
    seed_genres = seed_feat[1].get("genres", set())
    threshold_used = settings.playlist_max_candidate_distance
    genre_relevant: list[list] = []

    for threshold in [settings.playlist_max_candidate_distance, 0.85, 0.95, 1.0]:
        genre_relevant = _filter_by_threshold(candidate_features, seed_genres, threshold)
        threshold_used = threshold
        if len(genre_relevant) >= n:
            break

    if len(genre_relevant) <= n:
        return genre_relevant, "sa_all_candidates", threshold_used

    m = len(genre_relevant)
    n_pairs = n * (n - 1) // 2

    def energy(sel_idx: list[int]) -> float:
        sel = [genre_relevant[i] for i in sel_idx]
        avg_relevance = sum(get_distance(seed_feat, c) for c in sel) / n
        avg_diversity = sum(get_distance(sel[i], sel[j]) for i in range(n) for j in range(i + 1, n)) / n_pairs
        return avg_relevance - settings.sa_diversity_weight * avg_diversity

    # Initial random selection
    selected = list(random.sample(range(m), n))
    selected_set = set(selected)
    remaining = [i for i in range(m) if i not in selected_set]
    current_energy = energy(selected)

    T = settings.sa_temperature_start
    cooling = (settings.sa_temperature_end / settings.sa_temperature_start) ** (1.0 / settings.sa_iterations)

    for _ in range(settings.sa_iterations):
        out_pos = random.randrange(n)
        in_pos = random.randrange(len(remaining))

        new_selected = selected[:]
        new_selected[out_pos], remaining[in_pos] = remaining[in_pos], new_selected[out_pos]

        new_energy = energy(new_selected)
        delta = new_energy - current_energy

        if delta < 0 or random.random() < math.exp(-delta / T):
            selected = new_selected
            current_energy = new_energy
        else:
            # Revert swap in remaining
            remaining[in_pos] = new_selected[out_pos]

        T *= cooling

    fallback = f"sa_β{settings.sa_diversity_weight}_T{settings.sa_temperature_start}→{settings.sa_temperature_end}"
    return [genre_relevant[i] for i in selected], fallback, threshold_used
