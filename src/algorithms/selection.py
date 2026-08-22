"""
Pluggable selection strategies for build_playlist_from_seed.

Both take the same core inputs (candidate pool, seed, n) and return
(top_n, fallback_label, threshold_used). Neither touches HTTP or a global
settings singleton; every tunable comes in explicitly through the config
models in models.py, so both are usable standalone, from a script or a future
batch job, exactly as from the current FastAPI endpoint.
"""

import math
import random
from collections.abc import Generator

from src.algorithms.distance import get_distance, jaccard_distance
from src.algorithms.models import (
    DistanceWeights,
    GreedySelectionConfig,
    SAIterationEvent,
    SimulatedAnnealingConfig,
    ThresholdStepEvent,
)


def _filter_by_threshold(
    candidate_features: list[list],
    seed_genres: set[str],
    threshold: float,
) -> list[list]:
    return [c for c in candidate_features if jaccard_distance(seed_genres, c[1].get("genres", set())) <= threshold]


def select_greedy(
    candidate_features: list[list],
    seed_feat: list,
    candidate_tracks: dict[str, dict],
    n: int,
    config: GreedySelectionConfig,
) -> tuple[list[list], str, float, list[ThresholdStepEvent]]:
    """
    Walk candidates in distance order, enforce per-artist cap at selection time.
    Relax Jaccard threshold progressively until n tracks are found.
    Returns (top_n, fallback_label, threshold_used, threshold_trace).
    """
    seed_genres = seed_feat[1].get("genres", set())
    fallback = "genre_search"
    threshold_used = config.max_candidate_distance
    top_n: list[list] = []
    threshold_trace: list[ThresholdStepEvent] = []

    for threshold in [config.max_candidate_distance, 0.85, 0.95, 1.0]:
        genre_relevant = _filter_by_threshold(candidate_features, seed_genres, threshold)
        top_n = []
        artist_counts: dict[str, int] = {}
        for c in sorted(genre_relevant, key=lambda c: get_distance(seed_feat, c, config.weights)):
            artists = candidate_tracks.get(c[0], {}).get("artists", [])
            aid = artists[0]["id"] if artists else ""
            if artist_counts.get(aid, 0) >= config.max_tracks_per_artist:
                continue
            artist_counts[aid] = artist_counts.get(aid, 0) + 1
            top_n.append(c)
            if len(top_n) >= n:
                break
        threshold_used = threshold
        accepted = len(top_n) >= n
        threshold_trace.append(
            ThresholdStepEvent(threshold=threshold, candidates_passing=len(genre_relevant), accepted=accepted)
        )
        if threshold > config.max_candidate_distance:
            fallback = f"relaxed_threshold_{threshold}"
        if accepted:
            break

    return top_n, fallback, threshold_used, threshold_trace


def _energy(
    sel_idx: list[int],
    pool: list[list],
    seed_feat: list,
    weights: DistanceWeights,
    diversity_weight: float,
    n: int,
) -> float:
    """
    Energy of one candidate selection (lower is better).

    E(S) = avg_relevance(S) − diversity_weight × avg_pairwise_diversity(S)
         = mean dist(seed, sᵢ) − β × mean dist(sᵢ, sⱼ) for all pairs

    Standalone, no closures: every dependency is a parameter, so this is
    directly testable on its own without driving a full anneal.
    """
    sel = [pool[i] for i in sel_idx]
    avg_relevance = sum(get_distance(seed_feat, c, weights) for c in sel) / n
    n_pairs = n * (n - 1) // 2
    avg_diversity = sum(get_distance(sel[i], sel[j], weights) for i in range(n) for j in range(i + 1, n)) / n_pairs
    return avg_relevance - diversity_weight * avg_diversity


SAResult = tuple[list[list], str, float]


class SimulatedAnnealer:
    """
    Simulated annealing diverse subset selection for one seed + candidate pool.
    Standalone: no HTTP, no global settings singleton.

    Construction does the real setup: filters the candidate pool by genre
    threshold (relaxing progressively if needed), and — unless the pool is
    already small enough to return outright — picks the initial random
    selection and starting energy/temperature. run() only drives the
    iteration loop over that already-established state. This instance is
    single-use: construct a new one per anneal, exactly how it is already
    used today (PlaylistBuilderService builds a fresh SimulatedAnnealer per
    request; nothing reuses one instance across multiple candidate pools).

    run() is a generator: it yields one SAIterationEvent per iteration as the
    anneal actually proceeds, so a caller (the upcoming JSONL writer) can
    write each line out as it happens rather than waiting for every iteration
    to finish first. The final (top_n, fallback_label, threshold_used) is the
    generator's return value, delivered via StopIteration.value the same way
    `yield from` consumes it. Use run_to_completion() for the common case of
    wanting everything at once.

    Energy: see _energy() above. Accepts worse moves with prob e^(−ΔE/T), T
    cools from temperature_start to temperature_end.

    Escapes the greedy cap failure mode: greedy cannot undo an early popular-artist
    pick; SA can swap it out later if a more diverse set lowers energy.
    """

    def __init__(
        self,
        config: SimulatedAnnealingConfig,
        candidate_features: list[list],
        seed_feat: list,
        n: int,
    ) -> None:
        self._config = config
        self._seed_feat = seed_feat
        self._n = n

        seed_genres = seed_feat[1].get("genres", set())
        threshold_used = config.max_candidate_distance
        genre_relevant: list[list] = []
        threshold_trace: list[ThresholdStepEvent] = []
        for threshold in [config.max_candidate_distance, 0.85, 0.95, 1.0]:
            genre_relevant = _filter_by_threshold(candidate_features, seed_genres, threshold)
            threshold_used = threshold
            accepted = len(genre_relevant) >= n
            threshold_trace.append(
                ThresholdStepEvent(threshold=threshold, candidates_passing=len(genre_relevant), accepted=accepted)
            )
            if accepted:
                break

        self._genre_relevant = genre_relevant
        self._threshold_used = threshold_used
        self.threshold_trace = threshold_trace
        self._shortcut = len(genre_relevant) <= n
        if self._shortcut:
            return

        m = len(genre_relevant)
        self._selected = list(random.sample(range(m), n))
        selected_set = set(self._selected)
        self._remaining = [i for i in range(m) if i not in selected_set]
        self._current_energy = _energy(
            self._selected, self._genre_relevant, seed_feat, config.weights, config.diversity_weight, n
        )
        self._temperature = config.temperature_start
        self._cooling = (config.temperature_end / config.temperature_start) ** (1.0 / config.iterations)

    def run(self) -> Generator[SAIterationEvent, None, SAResult]:
        """Yields one SAIterationEvent per iteration; returns (top_n, fallback_label, threshold_used)."""
        if self._shortcut:
            return self._genre_relevant, "sa_all_candidates", self._threshold_used

        config = self._config
        n = self._n

        for iteration in range(config.iterations):
            out_pos = random.randrange(n)
            in_pos = random.randrange(len(self._remaining))

            out_idx = self._selected[out_pos]
            in_idx = self._remaining[in_pos]

            new_selected = self._selected[:]
            new_selected[out_pos] = in_idx

            new_energy = _energy(
                new_selected, self._genre_relevant, self._seed_feat, config.weights, config.diversity_weight, n
            )
            delta = new_energy - self._current_energy
            accepted = delta < 0 or random.random() < math.exp(-delta / self._temperature)

            if accepted:
                self._selected = new_selected
                self._remaining[in_pos] = out_idx
                self._current_energy = new_energy
            # else: selected and remaining are left exactly as they were,
            # the proposed swap is discarded.

            yield SAIterationEvent(
                iteration=iteration,
                temperature=self._temperature,
                energy=new_energy,
                accepted=accepted,
                out_track_id=self._genre_relevant[out_idx][0],
                in_track_id=self._genre_relevant[in_idx][0],
            )

            self._temperature *= self._cooling

        fallback = f"sa_β{config.diversity_weight}_T{config.temperature_start}→{config.temperature_end}"
        return [self._genre_relevant[i] for i in self._selected], fallback, self._threshold_used

    def run_to_completion(self) -> tuple[list[list], str, float, list[SAIterationEvent], list[ThresholdStepEvent]]:
        """Drains run(). Returns (top_n, fallback_label, threshold_used, sa_trace, threshold_trace)."""
        trace: list[SAIterationEvent] = []
        generator = self.run()
        while True:
            try:
                trace.append(next(generator))
            except StopIteration as stop:
                top_n, fallback, threshold_used = stop.value
                return top_n, fallback, threshold_used, trace, self.threshold_trace
