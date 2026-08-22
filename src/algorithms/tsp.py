"""
Genetic-algorithm TSP ordering. Pure: no HTTP, no global settings singleton.

Orders a set of tracks to minimize total distance between adjacent tracks,
using the same genre + release-year distance as the selection strategies.
"""

import random
from collections.abc import Generator

from src.algorithms.distance import get_distance
from src.algorithms.models import DistanceWeights, TSPGenerationEvent, TSPPopulationMember, TSPWalkEvent

# Graph type: track_id → {other_track_id → distance}
Graph = dict[str, dict[str, float]]


def _make_graph(data: list[list], weights: DistanceWeights) -> Graph:
    """Build adjacency graph where edge weight = distance between two tracks."""
    return {
        track[0]: {other[0]: get_distance(track, other, weights) for other in data if other[0] != track[0]}
        for track in data
    }


def _evaluate_walk(walk: list, graph: Graph) -> float:
    """Sum of distances between all adjacent track pairs in walk. O(n) dict lookup."""
    dist = 0.0
    for i in range(1, len(walk)):
        dist += graph[walk[i]][walk[i - 1]]
    return dist


def _get_walk(graph: Graph) -> list:
    """Random ordering of all tracks with distance score appended."""
    walk: list = list(graph.keys())
    random.shuffle(walk)
    walk.append(_evaluate_walk(walk, graph))
    return walk


def _sort_walks(walks: list[list]) -> list[list]:
    return sorted(walks, key=lambda w: w[-1])


def _apply_selection(population: list[list]) -> list[list]:
    selected = []
    for _ in range(len(population) // 2):
        tournament = random.sample(population, 3)
        selected.append(min(tournament, key=lambda w: w[-1]))
    return selected


def _apply_crossover(population: list[list], graph: Graph) -> list[list]:
    offspring = []
    for _ in range(len(population)):
        a = list(random.choice(population)[:-1])
        b = list(random.choice(population)[:-1])
        mid = max(len(a) // 2, 1)
        start = random.randrange(mid)
        child = a[start : start + mid]
        child += [x for x in b if x not in child]
        child.append(_evaluate_walk(child, graph))
        offspring.append(child)
    return offspring


def _mutate(walk: list, graph: Graph) -> list:
    body = walk[:-1]
    rotated = body[1:] + [body[0]]
    rotated.append(_evaluate_walk(rotated, graph))
    return rotated


def _apply_mutation(population: list[list], graph: Graph) -> list[list]:
    return [_mutate(w, graph) if random.random() < 0.5 else w for w in population]


def _apply_genetics(population: list[list], graph: Graph) -> list[list]:
    selected = _apply_selection(population)
    offspring = _apply_crossover(selected, graph)
    return _apply_mutation(selected + offspring, graph)


def _init_population(graph: Graph, size: int) -> list[list]:
    return _sort_walks([_get_walk(graph) for _ in range(size)])


TSPResult = tuple[list[str], float, float]


TSPTraceEvent = TSPWalkEvent | TSPGenerationEvent


class TSPOptimizer:
    """
    Genetic TSP ordering for one candidate pool, exposed the same shape as
    SimulatedAnnealer: construction does setup, run() is a generator, run_to_completion()
    drains it for the common case of wanting everything at once.

    A generation is the finest natural unit here — one full selection ->
    crossover -> mutation cycle over the whole population — there's no
    smaller meaningful step the way SA has one atomic swap per iteration.

    Content-addressed walk cache: run() yields the full population every
    generation (no truncation), but a distinct track ordering is only ever
    written once, as a TSPWalkEvent, the first time it's seen (generation 0's
    initial random population included). Every later TSPGenerationEvent
    references walks by walk_id instead of repeating their track ids —
    _apply_selection carries survivors forward unchanged and _apply_mutation
    leaves ~half the population untouched each generation, so most walks in
    generation g+1 are already-cached content from generation g or earlier.
    """

    def __init__(
        self,
        track_features: list[list],
        weights: DistanceWeights,
        population_size: int = 20,
        generations: int = 50,
    ) -> None:
        self._graph = _make_graph(track_features, weights)
        self._population = _init_population(self._graph, population_size)
        self._generations = generations
        self.initial_score = float(self._population[0][-1])
        self._walk_ids: dict[tuple[str, ...], int] = {}
        self._next_walk_id = 0

    def _process_generation(self, generation: int) -> list[TSPTraceEvent]:
        """Cache-miss walks (if any) followed by exactly one TSPGenerationEvent for the full population."""
        events: list[TSPTraceEvent] = []
        members: list[TSPPopulationMember] = []
        for walk in self._population:
            key = tuple(walk[:-1])
            walk_id = self._walk_ids.get(key)
            if walk_id is None:
                walk_id = self._next_walk_id
                self._walk_ids[key] = walk_id
                self._next_walk_id += 1
                events.append(TSPWalkEvent(walk_id=walk_id, track_ids=list(key)))
            members.append(TSPPopulationMember(walk_id=walk_id, score=float(walk[-1])))
        events.append(TSPGenerationEvent(generation=generation, members=members))
        return events

    def run(self) -> Generator[TSPTraceEvent, None, TSPResult]:
        """
        Yields TSPWalkEvents (cache misses) then one TSPGenerationEvent, per generation.
        generation 0 is the initial random population; 1..generations are evolved.
        Returns (ordered_ids, final_score, initial_score).
        """
        yield from self._process_generation(0)

        for generation in range(1, self._generations + 1):
            self._population = _apply_genetics(self._population, self._graph)
            self._population = _sort_walks(self._population)
            yield from self._process_generation(generation)

        best = self._population[0]
        return best[:-1], float(best[-1]), self.initial_score

    def run_to_completion(self) -> tuple[list[str], float, float, list[TSPTraceEvent]]:
        """Drains run(). Returns (ordered_ids, final_score, initial_score, trace)."""
        trace: list[TSPTraceEvent] = []
        generator = self.run()
        while True:
            try:
                trace.append(next(generator))
            except StopIteration as stop:
                ordered_ids, final_score, initial_score = stop.value
                return ordered_ids, final_score, initial_score, trace


def order_by_tsp(
    track_features: list[list],
    weights: DistanceWeights,
    population_size: int = 20,
    generations: int = 50,
) -> TSPResult:
    """
    Order tracks via genetic TSP to minimize total distance between adjacent tracks.
    Returns (ordered_track_ids, final_score, initial_score).

    Thin wrapper around TSPOptimizer for callers that don't need the
    per-generation trace (build_genre_playlist_tsp) — drains run_to_completion()
    and discards the trace.

    improvement_pct = (1 - final_score / initial_score) * 100
      0%            → algorithm made no progress; either population_size/generations too small,
                      or all tracks share identical genre+year (initial_score=0, guarded separately)
      20–40%        → moderate improvement, tracks fairly similar
      40–60%        → strong improvement, meaningful genre/year variance in pool
      >60%          → large variance, algorithm had lots of room to optimize

    generations: each generation runs one cycle of selection → crossover → mutation.
      More generations = more evolution cycles = closer to the optimal route, diminishing returns.
      Default 50 balances speed vs quality. Increase for larger track pools or higher accuracy.
    """
    ordered_ids, final_score, initial_score, _ = TSPOptimizer(
        track_features, weights, population_size, generations
    ).run_to_completion()
    return ordered_ids, final_score, initial_score
