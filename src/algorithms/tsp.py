"""
Genetic-algorithm TSP ordering. Pure: no HTTP, no global settings singleton.

Orders a set of tracks to minimize total distance between adjacent tracks,
using the same genre + release-year distance as the selection strategies.
"""

import random
from collections.abc import Callable, Generator
from dataclasses import dataclass, field

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


def _evaluate_walk(track_ids: tuple[str, ...], graph: Graph) -> float:
    """Sum of distances between all adjacent track pairs in walk. O(n) dict lookup."""
    dist = 0.0
    for i in range(1, len(track_ids)):
        dist += graph[track_ids[i]][track_ids[i - 1]]
    return dist


@dataclass
class Walk:
    """One candidate track ordering with its evaluated score and lineage.

    walk_id is always assigned at construction, via TSPOptimizer._register —
    never minted directly by the genetic operators below, since it must be
    content-addressed against every walk seen so far in the run (a survivor
    carried forward unchanged must resolve to its existing id, not a new
    one). See TSPOptimizer._register.
    """

    track_ids: tuple[str, ...]
    score: float
    walk_id: int
    parent_walk_ids: list[int] = field(default_factory=list)


Register = Callable[[tuple[str, ...], float, list[int]], Walk]


def _get_walk(graph: Graph) -> tuple[tuple[str, ...], float]:
    """Random ordering of all tracks with its evaluated score. Not yet registered — no lineage, no id."""
    track_ids = list(graph.keys())
    random.shuffle(track_ids)
    ids = tuple(track_ids)
    return ids, _evaluate_walk(ids, graph)


def _sort_walks(walks: list[Walk]) -> list[Walk]:
    return sorted(walks, key=lambda w: w.score)


def _apply_selection(population: list[Walk]) -> list[Walk]:
    """Tournament selection. Survivors are the same Walk objects, not copies —
    their existing walk_id/parent_walk_ids (from whenever they were first
    created) carry forward unchanged, no re-registration needed."""
    selected = []
    for _ in range(len(population) // 2):
        tournament = random.sample(population, 3)
        selected.append(min(tournament, key=lambda w: w.score))
    return selected


def _apply_crossover(population: list[Walk], graph: Graph, register: Register) -> list[Walk]:
    """Each child's parent_walk_ids = [a.walk_id, b.walk_id] — both parents are
    already-registered Walks (population here is always survivors from
    _apply_selection, whose walk_ids were resolved in a previous generation),
    so this never needs to wait for a later registration pass."""
    offspring = []
    for _ in range(len(population)):
        a = random.choice(population)
        b = random.choice(population)
        mid = max(len(a.track_ids) // 2, 1)
        start = random.randrange(mid)
        child_ids = list(a.track_ids[start : start + mid])
        child_ids += [x for x in b.track_ids if x not in child_ids]
        ids = tuple(child_ids)
        offspring.append(register(ids, _evaluate_walk(ids, graph), [a.walk_id, b.walk_id]))
    return offspring


def _mutate(walk: Walk, graph: Graph, register: Register) -> Walk:
    """parent_walk_ids = [walk.walk_id] — one edge, even when walk is itself a
    same-generation crossover child registered moments earlier; register()
    resolves that child's walk_id immediately at creation time, so it's
    already available here regardless of how walk was produced."""
    rotated = walk.track_ids[1:] + walk.track_ids[:1]
    return register(rotated, _evaluate_walk(rotated, graph), [walk.walk_id])


def _apply_mutation(population: list[Walk], graph: Graph, register: Register) -> list[Walk]:
    return [_mutate(w, graph, register) if random.random() < 0.5 else w for w in population]


def _apply_genetics(population: list[Walk], graph: Graph, register: Register) -> list[Walk]:
    selected = _apply_selection(population)
    offspring = _apply_crossover(selected, graph, register)
    return _apply_mutation(selected + offspring, graph, register)


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

    Content-addressed walk cache with lineage: every Walk is created by
    calling self._register(track_ids, score, parent_walk_ids) — injected into
    the otherwise-pure _apply_crossover/_apply_mutation as the `register`
    parameter, so a new walk_id (and its TSPWalkEvent) is minted the instant a
    genuinely new ordering appears, with its parents already known, rather
    than reconstructed after the fact by diffing populations across
    generations. A survivor carried forward unchanged (_apply_selection) or
    a walk whose content coincidentally already exists resolves to its
    existing walk_id instead of registering a duplicate — that's what keeps
    a full, untruncated population trace affordable: _apply_selection carries
    survivors forward unchanged and _apply_mutation leaves ~half the
    population untouched each generation, so most walks in generation g+1
    are already-cached content from generation g or earlier.
    """

    def __init__(
        self,
        track_features: list[list],
        weights: DistanceWeights,
        population_size: int = 20,
        generations: int = 50,
    ) -> None:
        self._graph = _make_graph(track_features, weights)
        self._generations = generations
        self._walk_registry: dict[tuple[str, ...], int] = {}
        self._next_walk_id = 0
        self._pending_walk_events: list[TSPWalkEvent] = []

        initial = [self._register(*_get_walk(self._graph), []) for _ in range(population_size)]
        self._population = _sort_walks(initial)
        self.initial_score = self._population[0].score

    def _register(self, track_ids: tuple[str, ...], score: float, parent_walk_ids: list[int]) -> Walk:
        """Resolve track_ids to a Walk with a stable, content-addressed walk_id.

        Reused content (survivor reappearing, or coincidental duplicate
        ordering) resolves to the walk_id from whenever it was first seen —
        no new TSPWalkEvent, the canonical lineage is whatever was recorded
        at that first registration. Genuinely new content mints the next
        walk_id and queues a TSPWalkEvent, drained by _process_generation.
        """
        existing_id = self._walk_registry.get(track_ids)
        if existing_id is not None:
            return Walk(track_ids=track_ids, score=score, walk_id=existing_id, parent_walk_ids=parent_walk_ids)

        walk_id = self._next_walk_id
        self._next_walk_id += 1
        self._walk_registry[track_ids] = walk_id
        self._pending_walk_events.append(
            TSPWalkEvent(walk_id=walk_id, track_ids=list(track_ids), parent_walk_ids=parent_walk_ids)
        )
        return Walk(track_ids=track_ids, score=score, walk_id=walk_id, parent_walk_ids=parent_walk_ids)

    def _process_generation(self, generation: int) -> list[TSPTraceEvent]:
        """Drains whatever TSPWalkEvents were queued since the last generation,
        followed by exactly one TSPGenerationEvent for the full population."""
        events: list[TSPTraceEvent] = list(self._pending_walk_events)
        self._pending_walk_events.clear()
        members = [TSPPopulationMember(walk_id=w.walk_id, score=w.score) for w in self._population]
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
            self._population = _apply_genetics(self._population, self._graph, self._register)
            self._population = _sort_walks(self._population)
            yield from self._process_generation(generation)

        best = self._population[0]
        return list(best.track_ids), best.score, self.initial_score

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
