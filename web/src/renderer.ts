/**
 * Ties the view model (projector.ts) and pure blob simulation (playback.ts)
 * to an actual <canvas> and a requestAnimationFrame loop. This is the one
 * file in the pipeline that isn't unit-tested — Canvas 2D drawing isn't
 * meaningfully testable without a browser (or a jsdom+canvas mock this
 * project deliberately isn't pulling in for one file). Verified instead by
 * running it in a real browser against real backend data, same as the
 * gooey-canvas prototype was.
 *
 * Playback, in order:
 *   1. "candidates" — every candidate (+ the seed) drifts in as an unselected
 *      blob for a couple of seconds, so a viewer sees the actual pool size
 *      before anything gets highlighted.
 *   2. "sa" — only if the trace has an SA episode with a reconstructed
 *      selection trajectory (see projector.ts). Steps through
 *      selectionsAfter one iteration at a time at a configurable rate.
 *      Selected tracks grow (applySelection) *and* get pulled toward the
 *      seed's current position (applyAttraction) — the actual visual
 *      "convergence" signal. Without the attraction, selection only
 *      changed radius; blobs drifted randomly regardless of whether they
 *      were selected, so nothing ever looked like it was converging, just
 *      jittering in place. The *selected* blobs' jitter is also scaled by
 *      the current iteration's temperature (SimulatedAnnealingConfig cools
 *      from 1.0 to 0.01), so the converging cluster visibly settles as the
 *      anneal cools — unselected candidates keep full ambient jitter the
 *      whole time regardless (see stepPhysics's selectedJitterScale),
 *      since the anneal's temperature has nothing to do with candidates
 *      that were never part of the current selection.
 *   3. "tsp" — only if the trace has any tsp_generation events (present
 *      for both strategies whenever len(top_n) >= 3, see order_by_tsp).
 *      Entering this phase prunes down to exactly the final selected set
 *      (pruneTo) — candidates that were never selected have nothing to do
 *      with TSP and must not keep sitting around being affected by
 *      TSP-phase parameters meant only for the selected set, same lesson
 *      as the jitterScale scoping bug. Each generation's best walk
 *      (members[0] — already sorted ascending by score, guaranteed by the
 *      backend's _sort_walks, see tsp.py) gets a "chase": a highlight
 *      (applyHighlight, a flag kept deliberately separate from `selected`
 *      — see BlobState.highlighted) steps through its trackIds in order,
 *      one track at a time, before advancing to the next generation.
 *      Screen-space blob position is NOT used to represent tour distance
 *      here — the blobs' 2D positions are physics-simulated drift
 *      coordinates with no relationship to the actual genre+year distance
 *      TSP is optimizing, so a shrinking on-screen path would be a
 *      misleading metaphor. The real tsp_score/improvement is reported
 *      through onStatusChange instead, as an actual number, not inferred
 *      from geometry.
 *   4. "final" — highlights the actual final playlist (pulled toward the
 *      seed the same way) and stays there.
 *
 * Also reports, every frame, via onStatusChange: SA energy during "sa",
 * TSP generation/score/improvement during "tsp"; and via onStatsChange:
 * genre mix / year spread / avg distance from seed (stats.ts) for whatever
 * track set is currently emphasized; and via onGenerationDiff: which
 * TSP walk_ids appeared/disappeared this generation (walkLineage.ts),
 * for a DOM "tree list" view of population turnover.
 */

import type { CandidateInfo, PlaylistDNAViewModel, SeedInfo, TSPGenerationFrame } from "./projector";
import {
  applyAttraction,
  applyHighlight,
  applySelection,
  createBlobs,
  pruneTo,
  stepPhysics,
  type BlobSeed,
  type Blobs,
} from "./playback";
import { computeStats, type DNAStats } from "./stats";
import { diffGenerations, type GenerationDiff } from "./walkLineage";

export type Phase = "candidates" | "sa" | "tsp" | "final";

export interface PlaybackStatus {
  phase: Phase;
  saIteration: number;
  saTotal: number;
  saEnergy: number | null;
  tspGeneration: number;
  tspGenerationsTotal: number;
  tspBestScore: number | null;
  tspInitialScore: number | null;
}

export interface RendererOptions {
  /** How long the candidate intro phase lasts before SA playback (or TSP/final, if no SA trace) starts. */
  candidateIntroMs?: number;
  /** Milliseconds of simulated time per SA iteration advanced. Lower = faster playback. */
  msPerIteration?: number;
  /** Milliseconds of simulated time each TSP generation's chase gets, split evenly across its walk's tracks. */
  msPerGeneration?: number;
  onStatusChange?: (status: PlaybackStatus) => void;
  onStatsChange?: (stats: DNAStats) => void;
  onGenerationDiff?: (diff: GenerationDiff) => void;
}

const DEFAULT_CANDIDATE_INTRO_MS = 2000;
const DEFAULT_MS_PER_ITERATION = 15;
const DEFAULT_MS_PER_GENERATION = 800;
/** Fraction of the remaining gap to the seed a selected blob closes per second. */
const ATTRACTION_STRENGTH = 1.5;
/** Floor for the temperature-derived jitter scale — never fully freeze, that reads as broken, not converged. */
const MIN_JITTER_SCALE = 0.08;

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly width: number;
  private readonly height: number;
  private readonly viewModel: PlaylistDNAViewModel;
  private readonly candidateIntroMs: number;
  private readonly msPerIteration: number;
  private readonly msPerGeneration: number;
  private readonly onStatusChange: RendererOptions["onStatusChange"];
  private readonly onStatsChange: RendererOptions["onStatsChange"];
  private readonly onGenerationDiff: RendererOptions["onGenerationDiff"];
  /** Precomputed once — diffGenerations takes the whole array, no reason to recompute it every frame. */
  private readonly generationDiffs: GenerationDiff[];

  private blobs: Blobs;
  private phase: Phase = "candidates";
  private phaseElapsedMs = 0;
  private saIterationIndex = -1;
  private saAccumulatorMs = 0;
  private tspGenerationIndex = -1;
  private tspChaseIndex = -1;
  private tspChaseAccumulatorMs = 0;

  private playing = false;
  private rafHandle: number | null = null;
  private lastTimestamp = 0;

  constructor(canvas: HTMLCanvasElement, viewModel: PlaylistDNAViewModel, options: RendererOptions = {}) {
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("2D canvas context not available");
    }
    this.ctx = ctx;
    this.width = canvas.width;
    this.height = canvas.height;
    this.viewModel = viewModel;
    this.candidateIntroMs = options.candidateIntroMs ?? DEFAULT_CANDIDATE_INTRO_MS;
    this.msPerIteration = options.msPerIteration ?? DEFAULT_MS_PER_ITERATION;
    this.msPerGeneration = options.msPerGeneration ?? DEFAULT_MS_PER_GENERATION;
    this.onStatusChange = options.onStatusChange;
    this.onStatsChange = options.onStatsChange;
    this.onGenerationDiff = options.onGenerationDiff;
    this.generationDiffs = diffGenerations(viewModel.tspGenerations);

    const entries: BlobSeed[] = [
      { id: viewModel.seed.trackId, genres: viewModel.seed.genres },
      ...[...viewModel.candidates.values()].map((c) => ({ id: c.trackId, genres: c.genres })),
    ];
    this.blobs = createBlobs(entries, this.width, this.height);
    this.draw();
    this.reportStats([]);
  }

  start(): void {
    if (this.playing) return;
    this.playing = true;
    this.lastTimestamp = performance.now();
    this.rafHandle = requestAnimationFrame(this.tick);
  }

  pause(): void {
    this.playing = false;
    if (this.rafHandle !== null) {
      cancelAnimationFrame(this.rafHandle);
      this.rafHandle = null;
    }
  }

  get isPlaying(): boolean {
    return this.playing;
  }

  private readonly tick = (timestamp: number): void => {
    const dtMs = timestamp - this.lastTimestamp;
    this.lastTimestamp = timestamp;

    this.advance(dtMs);
    this.draw();
    this.reportStatus();

    if (this.playing) {
      this.rafHandle = requestAnimationFrame(this.tick);
    }
  };

  private advance(dtMs: number): void {
    this.blobs = stepPhysics(this.blobs, dtMs, this.width, this.height, Math.random, this.currentJitterScale());

    const seed = this.blobs.get(this.viewModel.seed.trackId);
    if (seed) {
      this.blobs = applyAttraction(this.blobs, { x: seed.x, y: seed.y }, ATTRACTION_STRENGTH, dtMs);
    }

    switch (this.phase) {
      case "candidates":
        this.phaseElapsedMs += dtMs;
        if (this.phaseElapsedMs >= this.candidateIntroMs) {
          this.enterSAPhaseOrSkipToTSP();
        }
        break;
      case "sa":
        this.advanceSA(dtMs);
        break;
      case "tsp":
        this.advanceTSP(dtMs);
        break;
      case "final":
        break; // final selection already applied, nothing more to advance
    }
  }

  /**
   * How much *new* jitter to inject this frame into *selected* blobs only
   * (see stepPhysics's selectedJitterScale param — unselected blobs always
   * get full ambient jitter regardless of this value, deliberately: this
   * represents the anneal's temperature, which has nothing to do with
   * candidates that were never selected). Derived from the current SA
   * iteration's temperature (cools from 1.0 toward 0.01 by construction —
   * see SimulatedAnnealingConfig). Outside the SA phase there's no
   * temperature to read, so this returns 1.
   */
  private currentJitterScale(): number {
    if (this.phase !== "sa" || this.saIterationIndex < 0) return 1;
    const episode = this.lastSAEpisode();
    const temperature = episode?.iterations[this.saIterationIndex]?.temperature;
    return temperature === undefined ? 1 : Math.max(temperature, MIN_JITTER_SCALE);
  }

  private lastSAEpisode() {
    const episodes = this.viewModel.saEpisodes;
    return episodes.length > 0 ? episodes[episodes.length - 1] : undefined;
  }

  private enterSAPhaseOrSkipToTSP(): void {
    const episode = this.lastSAEpisode();
    if (!episode || !episode.selectionsAfter || !episode.initialSelection) {
      this.enterTSPPhaseOrSkipToFinal();
      return;
    }
    this.phase = "sa";
    this.saIterationIndex = -1;
    this.saAccumulatorMs = 0;
    this.blobs = applySelection(this.blobs, episode.initialSelection);
    this.reportStats([...episode.initialSelection]);
  }

  private advanceSA(dtMs: number): void {
    const episode = this.lastSAEpisode();
    if (!episode || !episode.selectionsAfter) {
      this.enterTSPPhaseOrSkipToFinal();
      return;
    }

    this.saAccumulatorMs += dtMs;
    while (this.saAccumulatorMs >= this.msPerIteration && this.saIterationIndex < episode.iterations.length - 1) {
      this.saAccumulatorMs -= this.msPerIteration;
      this.saIterationIndex++;
      const selection = episode.selectionsAfter[this.saIterationIndex]!;
      this.blobs = applySelection(this.blobs, selection);
      this.reportStats([...selection]);
    }

    if (this.saIterationIndex >= episode.iterations.length - 1) {
      this.enterTSPPhaseOrSkipToFinal();
    }
  }

  /**
   * Prunes to the fixed final set (TSP never changes membership, only
   * order) and starts chasing generation 0's best walk. If the trace has
   * no TSP generations at all (pool was too small for TSP to run, see
   * build_playlist_from_seed step 6), skips straight to "final".
   */
  private enterTSPPhaseOrSkipToFinal(): void {
    if (this.viewModel.tspGenerations.length === 0) {
      this.enterFinalPhase();
      return;
    }

    this.phase = "tsp";
    this.tspGenerationIndex = 0;
    this.tspChaseIndex = -1;
    this.tspChaseAccumulatorMs = 0;

    const finalIds = new Set(this.viewModel.final.trackIds);
    this.blobs = pruneTo(this.blobs, finalIds);
    this.blobs = applySelection(this.blobs, finalIds);
    this.reportGenerationDiff(0);
    this.reportBestWalkStats(0);
  }

  private advanceTSP(dtMs: number): void {
    const generations = this.viewModel.tspGenerations;
    const generation: TSPGenerationFrame | undefined = generations[this.tspGenerationIndex];
    if (!generation) {
      this.enterFinalPhase();
      return;
    }

    // members[0] is already the lowest-score (best) walk in this
    // generation — guaranteed by the backend sorting the population
    // before building each TSPGenerationEvent (see TSPOptimizer in tsp.py).
    const bestWalk = generation.members[0]?.walk;
    if (!bestWalk || bestWalk.trackIds.length === 0) {
      this.enterFinalPhase();
      return;
    }

    const stepMs = this.msPerGeneration / bestWalk.trackIds.length;
    this.tspChaseAccumulatorMs += dtMs;
    while (this.tspChaseAccumulatorMs >= stepMs && this.tspChaseIndex < bestWalk.trackIds.length - 1) {
      this.tspChaseAccumulatorMs -= stepMs;
      this.tspChaseIndex++;
      this.blobs = applyHighlight(this.blobs, bestWalk.trackIds[this.tspChaseIndex] ?? null);
    }

    if (this.tspChaseIndex >= bestWalk.trackIds.length - 1) {
      this.tspGenerationIndex++;
      this.tspChaseIndex = -1;
      this.tspChaseAccumulatorMs = 0;

      if (this.tspGenerationIndex >= generations.length) {
        this.blobs = applyHighlight(this.blobs, null);
        this.enterFinalPhase();
      } else {
        this.reportGenerationDiff(this.tspGenerationIndex);
        this.reportBestWalkStats(this.tspGenerationIndex);
      }
    }
  }

  private reportGenerationDiff(generationIndex: number): void {
    if (!this.onGenerationDiff) return;
    const diff = this.generationDiffs[generationIndex];
    if (diff) this.onGenerationDiff(diff);
  }

  private reportBestWalkStats(generationIndex: number): void {
    const bestWalk = this.viewModel.tspGenerations[generationIndex]?.members[0]?.walk;
    if (bestWalk) this.reportStats(bestWalk.trackIds);
  }

  private enterFinalPhase(): void {
    this.phase = "final";
    this.blobs = applyHighlight(this.blobs, null);
    this.blobs = applySelection(this.blobs, new Set(this.viewModel.final.trackIds));
    this.reportStats(this.viewModel.final.trackIds);
  }

  private reportStats(activeTrackIds: readonly string[]): void {
    if (!this.onStatsChange) return;
    this.onStatsChange(computeStats(activeTrackIds, this.viewModel.candidates, this.viewModel.seed));
  }

  private draw(): void {
    this.ctx.clearRect(0, 0, this.width, this.height);
    const seedId = this.viewModel.seed.trackId;

    for (const blob of this.blobs.values()) {
      this.ctx.beginPath();
      this.ctx.arc(blob.x, blob.y, blob.radius, 0, Math.PI * 2);
      this.ctx.fillStyle = blob.color;
      this.ctx.fill();

      if (blob.highlighted) {
        this.ctx.lineWidth = 4;
        this.ctx.strokeStyle = "#ffd93d";
        this.ctx.stroke();
      } else if (blob.id === seedId) {
        this.ctx.lineWidth = 3;
        this.ctx.strokeStyle = "white";
        this.ctx.stroke();
      }
    }
  }

  private reportStatus(): void {
    if (!this.onStatusChange) return;
    const saEpisode = this.lastSAEpisode();
    const saIter = saEpisode?.iterations[this.saIterationIndex];
    const currentGeneration = this.viewModel.tspGenerations[this.tspGenerationIndex];
    const bestMember = currentGeneration?.members[0];
    const firstGeneration = this.viewModel.tspGenerations[0];
    const initialBestMember = firstGeneration?.members[0];

    this.onStatusChange({
      phase: this.phase,
      saIteration: this.saIterationIndex + 1,
      saTotal: saEpisode?.iterations.length ?? 0,
      saEnergy: saIter?.energy ?? null,
      tspGeneration: this.tspGenerationIndex + 1,
      tspGenerationsTotal: this.viewModel.tspGenerations.length,
      tspBestScore: this.phase === "final" ? this.viewModel.final.tspScore : (bestMember?.score ?? null),
      tspInitialScore: initialBestMember?.score ?? null,
    });
  }
}
