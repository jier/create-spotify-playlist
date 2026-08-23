/**
 * Event log -> view model. Pure functions: TraceEvent[] in, a
 * PlaylistDNAViewModel out. No DOM, no Canvas, no rendering — this is the
 * "reducer" half of the split we agreed on (see WORKLOG.md Phase 17): a
 * renderer consumes what this file produces, it never touches TraceEvent
 * directly.
 *
 * Two things this module does that are more than a pass-through relabel:
 *
 * 1. Resolves tsp_walk / tsp_generation references. The backend writes a
 *    walk's track ids exactly once (content-addressed cache, see
 *    src/algorithms/tsp.py's TSPOptimizer) and every generation references
 *    walks by walk_id. buildViewModel joins these back together so a
 *    renderer never has to know the trace was normalized in the first
 *    place.
 *
 * 2. Reconstructs the SA-selected track set at every iteration. A
 *    sa_iteration event only records what swapped (out_track_id ->
 *    in_track_id); it does not record the full selection at that point.
 *    The only anchor available is the *final* result. Walking the trace
 *    backward from there — undoing each accepted swap in reverse — is
 *    sound because TSP only reorders the SA-selected set, it never changes
 *    its membership, and the seed is prepended afterward, outside the SA
 *    selection entirely. See reconstructLastEpisodeSelections.
 *
 *    This only works for whichever SA run actually produced the final
 *    result. If the discography fallback triggered, the trace can contain
 *    a second, independent anneal over a larger candidate pool, and its
 *    sa_iteration events restart from iteration 0 — a real signal, not
 *    noise, that a completely different anneal began. splitIntoSAEpisodes
 *    detects that restart and treats each anneal as its own episode; only
 *    the *last* episode gets a selection reconstruction, because it is the
 *    only one anchored to the final event. Earlier, abandoned episodes
 *    are still exposed (iteration/temperature/energy/swap), just without
 *    a `selectionsAfter` trajectory — there is nothing sound to anchor it
 *    to.
 */

import type { TraceEvent } from "./traceEvent";

export interface SeedInfo {
  trackId: string;
  genres: string[];
  releaseYear: number;
}

export interface CandidateInfo {
  trackId: string;
  name: string;
  artistName: string;
  artistId: string | null;
  genres: string[];
  releaseYear: number;
}

export interface ThresholdStepFrame {
  threshold: number;
  candidatesPassing: number;
  accepted: boolean;
}

export interface SAIterationFrame {
  iteration: number;
  temperature: number;
  energy: number;
  accepted: boolean;
  outTrackId: string;
  inTrackId: string;
}

export interface SAEpisode {
  iterations: SAIterationFrame[];
  /**
   * The full selected-track-id set immediately after each iteration in
   * this episode, same length/order as `iterations`. Only present on the
   * episode that actually produced the final result — see module docstring.
   */
  selectionsAfter?: ReadonlySet<string>[];
  /** The selection immediately before this episode's first iteration. Set iff selectionsAfter is. */
  initialSelection?: ReadonlySet<string>;
}

export interface TSPWalk {
  walkId: number;
  trackIds: string[];
  parentWalkIds: number[];
}

export interface TSPGenerationFrame {
  generation: number;
  members: Array<{ walk: TSPWalk; score: number }>;
}

export interface FinalResult {
  trackIds: string[];
  tspScore: number;
  initialScore: number;
  improvementPct: number;
}

export interface PlaylistDNAViewModel {
  seed: SeedInfo;
  candidates: Map<string, CandidateInfo>;
  thresholdSteps: ThresholdStepFrame[];
  saEpisodes: SAEpisode[];
  tspWalks: Map<number, TSPWalk>;
  tspGenerations: TSPGenerationFrame[];
  final: FinalResult;
}

export function buildViewModel(events: readonly TraceEvent[]): PlaylistDNAViewModel {
  let seed: SeedInfo | undefined;
  let final: FinalResult | undefined;
  const candidates = new Map<string, CandidateInfo>();
  const thresholdSteps: ThresholdStepFrame[] = [];
  const rawSAIterations: SAIterationFrame[] = [];
  const tspWalks = new Map<number, TSPWalk>();
  const tspGenerations: TSPGenerationFrame[] = [];

  for (const event of events) {
    switch (event.stage) {
      case "seed":
        seed = { trackId: event.track_id, genres: event.genres, releaseYear: event.release_year };
        break;

      case "candidate":
        candidates.set(event.track_id, {
          trackId: event.track_id,
          name: event.name,
          artistName: event.artist_name,
          artistId: event.artist_id,
          genres: event.genres,
          releaseYear: event.release_year,
        });
        break;

      case "threshold_step":
        thresholdSteps.push({
          threshold: event.threshold,
          candidatesPassing: event.candidates_passing,
          accepted: event.accepted,
        });
        break;

      case "sa_iteration":
        rawSAIterations.push({
          iteration: event.iteration,
          temperature: event.temperature,
          energy: event.energy,
          accepted: event.accepted,
          outTrackId: event.out_track_id,
          inTrackId: event.in_track_id,
        });
        break;

      case "tsp_walk":
        tspWalks.set(event.walk_id, {
          walkId: event.walk_id,
          trackIds: event.track_ids,
          parentWalkIds: event.parent_walk_ids,
        });
        break;

      case "tsp_generation":
        tspGenerations.push({
          generation: event.generation,
          members: event.members.map((member) => {
            const walk = tspWalks.get(member.walk_id);
            if (!walk) {
              throw new Error(
                `tsp_generation ${event.generation} references walk_id ${member.walk_id} before it was written`,
              );
            }
            return { walk, score: member.score };
          }),
        });
        break;

      case "final":
        final = {
          trackIds: event.track_ids,
          tspScore: event.tsp_score,
          initialScore: event.initial_score,
          improvementPct: event.improvement_pct,
        };
        break;
    }
  }

  if (!seed) throw new Error("trace has no seed event");
  if (!final) throw new Error("trace has no final event");

  const saEpisodes = splitIntoSAEpisodes(rawSAIterations);
  reconstructLastEpisodeSelections(saEpisodes, final, seed);

  return { seed, candidates, thresholdSteps, saEpisodes, tspWalks, tspGenerations, final };
}

/**
 * Groups a flat sa_iteration stream into independent anneal episodes. A new
 * episode starts whenever `iteration` fails to strictly increase from the
 * previous event — within one continuous SimulatedAnnealer.run(), iteration
 * always increases by exactly 1 (see SimulatedAnnealer.run in
 * src/algorithms/selection.py), so any non-increase is a real restart, not
 * noise: it means the discography fallback path re-ran a second anneal.
 */
export function splitIntoSAEpisodes(iterations: readonly SAIterationFrame[]): SAEpisode[] {
  if (iterations.length === 0) return [];

  const episodes: SAIterationFrame[][] = [[iterations[0]!]];
  for (let i = 1; i < iterations.length; i++) {
    const prev = iterations[i - 1]!;
    const curr = iterations[i]!;
    if (curr.iteration <= prev.iteration) {
      episodes.push([curr]);
    } else {
      episodes[episodes.length - 1]!.push(curr);
    }
  }
  return episodes.map((iters) => ({ iterations: iters }));
}

/**
 * Anchors the last SA episode to the final result and walks it backward,
 * undoing each accepted swap, to reconstruct the full selected-track-id set
 * after every iteration (and the true initial random selection before the
 * first one). Mutates the last element of `episodes` in place.
 *
 * Sound because: TSP only reorders the SA-selected set, never changes its
 * membership, and the seed is prepended afterward — so
 * final.trackIds minus seed.trackId is exactly the set the last SA episode
 * converged to.
 */
export function reconstructLastEpisodeSelections(episodes: SAEpisode[], final: FinalResult, seed: SeedInfo): void {
  if (episodes.length === 0) return;

  const lastEpisode = episodes[episodes.length - 1]!;
  const n = lastEpisode.iterations.length;
  const selectionsAfter: ReadonlySet<string>[] = new Array(n);
  const current = new Set(final.trackIds.filter((id) => id !== seed.trackId));

  for (let i = n - 1; i >= 0; i--) {
    selectionsAfter[i] = new Set(current);
    const iter = lastEpisode.iterations[i]!;
    if (iter.accepted) {
      current.delete(iter.inTrackId);
      current.add(iter.outTrackId);
    }
  }

  lastEpisode.selectionsAfter = selectionsAfter;
  lastEpisode.initialSelection = new Set(current);
}
