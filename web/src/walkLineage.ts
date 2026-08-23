/**
 * Pure generation-to-generation diffing of the TSP population: which
 * walk_ids are newly alive this generation, which ones that were alive
 * are no longer part of the population, and which are currently alive.
 *
 * This drives the "tree list" DOM view: a live list of currently-active
 * track orderings that grows as new ones appear (crossover/mutation
 * producing a genuinely new ordering) and prunes as ones stop surviving
 * tournament selection — a real, direct read of population turnover, not
 * a cosmetic effect. Population *size* stays constant every generation
 * (see TSPGenerationEvent's docstring), what changes is *which* orderings
 * currently make it up; this is what actually shows that.
 */

import type { TSPGenerationFrame } from "./projector";

export interface GenerationDiff {
  generation: number;
  /** walk_ids alive this generation that weren't alive last generation (or, for generation 0, every walk_id present). */
  appeared: number[];
  /** walk_ids alive last generation that are no longer alive this generation. Empty for generation 0. */
  disappeared: number[];
  /** every walk_id alive this generation. */
  alive: number[];
}

export function diffGenerations(generations: readonly TSPGenerationFrame[]): GenerationDiff[] {
  const diffs: GenerationDiff[] = [];
  let previousAlive = new Set<number>();

  for (const generation of generations) {
    const alive = new Set(generation.members.map((member) => member.walk.walkId));
    const appeared = [...alive].filter((id) => !previousAlive.has(id));
    const disappeared = [...previousAlive].filter((id) => !alive.has(id));

    diffs.push({ generation: generation.generation, appeared, disappeared, alive: [...alive] });
    previousAlive = alive;
  }

  return diffs;
}
