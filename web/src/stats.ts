/**
 * The "other DNA facets" readouts: genre mix, year spread, and average
 * distance from the seed for whatever track set is currently "in the
 * mix" (the SA-reconstructed selection at a given iteration, a TSP
 * generation's best walk, or the final result). Pure — the renderer calls
 * this each time the active set changes and hands the result to a DOM
 * callback; no DOM/Canvas in this file itself.
 */

import { distance } from "./distance";
import type { CandidateInfo, SeedInfo } from "./projector";

export interface GenreCount {
  genre: string;
  count: number;
}

export interface DNAStats {
  trackCount: number;
  /** Sorted descending by count, ties broken alphabetically — stable output for a UI list. */
  genreCounts: GenreCount[];
  yearMin: number | null;
  yearMax: number | null;
  /** Average distance (see distance.ts) from the seed over every non-seed track in the set. null if there are none. */
  avgDistanceFromSeed: number | null;
}

interface Resolved {
  id: string;
  genres: readonly string[];
  releaseYear: number;
}

function resolve(id: string, candidates: ReadonlyMap<string, CandidateInfo>, seed: SeedInfo): Resolved | undefined {
  if (id === seed.trackId) {
    return { id, genres: seed.genres, releaseYear: seed.releaseYear };
  }
  const candidate = candidates.get(id);
  return candidate ? { id, genres: candidate.genres, releaseYear: candidate.releaseYear } : undefined;
}

/**
 * trackIds not found in `candidates` and not the seed itself are silently
 * skipped (rather than throwing) — this runs every animation frame against
 * whatever the current selection/walk happens to be, a single unresolved
 * id shouldn't take down the stats panel.
 */
export function computeStats(
  trackIds: readonly string[],
  candidates: ReadonlyMap<string, CandidateInfo>,
  seed: SeedInfo,
): DNAStats {
  const resolved = trackIds
    .map((id) => resolve(id, candidates, seed))
    .filter((entry): entry is Resolved => entry !== undefined);

  const genreCountMap = new Map<string, number>();
  for (const entry of resolved) {
    for (const genre of entry.genres) {
      genreCountMap.set(genre, (genreCountMap.get(genre) ?? 0) + 1);
    }
  }
  const genreCounts = [...genreCountMap.entries()]
    .map(([genre, count]) => ({ genre, count }))
    .sort((a, b) => b.count - a.count || a.genre.localeCompare(b.genre));

  const years = resolved.map((entry) => entry.releaseYear).filter((year) => year > 0);
  const yearMin = years.length > 0 ? Math.min(...years) : null;
  const yearMax = years.length > 0 ? Math.max(...years) : null;

  const nonSeed = resolved.filter((entry) => entry.id !== seed.trackId);
  const seedInput = { genres: seed.genres, releaseYear: seed.releaseYear };
  const avgDistanceFromSeed =
    nonSeed.length > 0 ? nonSeed.reduce((sum, entry) => sum + distance(entry, seedInput), 0) / nonSeed.length : null;

  return { trackCount: resolved.length, genreCounts, yearMin, yearMax, avgDistanceFromSeed };
}
