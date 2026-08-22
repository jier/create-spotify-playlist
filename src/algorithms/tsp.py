"""
Genetic-algorithm TSP ordering. Pure: no HTTP, no global settings singleton.

Orders a set of tracks to minimize total distance between adjacent tracks,
using the same genre + release-year distance as the selection strategies.
"""

import random

from src.algorithms.distance import get_distance
from src.algorithms.models import DistanceWeights

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


def order_by_tsp(
    track_features: list[list],
    weights: DistanceWeights,
    population_size: int = 20,
    generations: int = 50,
) -> tuple[list[str], float, float]:
    """
    Order tracks via genetic TSP to minimize total distance between adjacent tracks.
    Returns (ordered_track_ids, final_score, initial_score).

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
    graph = _make_graph(track_features, weights)
    population = _init_population(graph, population_size)
    initial_score = float(population[0][-1])
    for _ in range(generations):
        population = _apply_genetics(population, graph)
        population = _sort_walks(population)
    best = population[0]
    return best[:-1], float(best[-1]), initial_score
