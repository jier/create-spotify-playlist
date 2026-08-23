/**
 * Mirrors src/algorithms/distance.py so the frontend can compute
 * "distance from seed" for a stats readout — the backend's own distance
 * values (used inside select_greedy/SimulatedAnnealer/order_by_tsp) are
 * never serialized into the trace, only their *effects* (which tracks got
 * selected, what order) are, so there's nothing to read off the wire for
 * this — it has to be recomputed here from the genre/year fields that
 * *are* in every seed/candidate/tsp_walk event.
 *
 * Honest limitation, not hidden: DEFAULT_WEIGHTS below are
 * settings.playlist_genre_weight / settings.playlist_year_weight's actual
 * default values, hardcoded — because those are server *configuration*,
 * not per-run *data*, so they were never part of the wire protocol either
 * (same reasoning DistanceWeights/GreedySelectionConfig/
 * SimulatedAnnealingConfig were excluded from codegen, see
 * generate_ts_models.py). If a run was ever built with non-default
 * weights, this stats readout would silently diverge slightly from what
 * the backend actually optimized for. Fine for an illustrative "how far
 * is this from the seed" readout; not presented as an exact reproduction.
 */

export interface DistanceWeights {
  genreWeight: number;
  yearWeight: number;
}

/** settings.playlist_genre_weight / settings.playlist_year_weight's defaults, see src/settings.py. */
export const DEFAULT_WEIGHTS: DistanceWeights = { genreWeight: 1.0, yearWeight: 0.5 };

export function jaccardDistance(genresA: ReadonlySet<string>, genresB: ReadonlySet<string>): number {
  const union = new Set([...genresA, ...genresB]);
  if (union.size === 0) return 1.0;
  let intersectionSize = 0;
  for (const g of genresA) {
    if (genresB.has(g)) intersectionSize++;
  }
  return 1.0 - intersectionSize / union.size;
}

export interface DistanceInput {
  genres: readonly string[];
  releaseYear: number;
}

export function distance(a: DistanceInput, b: DistanceInput, weights: DistanceWeights = DEFAULT_WEIGHTS): number {
  const genreDist = jaccardDistance(new Set(a.genres), new Set(b.genres));
  const yearDist = Math.min(Math.abs(a.releaseYear - b.releaseYear) / 50, 1.0);
  return weights.genreWeight * genreDist + weights.yearWeight * yearDist;
}
