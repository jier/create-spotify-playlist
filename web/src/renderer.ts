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
 *      selectionsAfter one iteration at a time at a configurable rate,
 *      highlighting (grows + a distinct radius, via playback.ts's
 *      applySelection) whichever tracks are currently selected.
 *   3. "final" — highlights the actual final playlist and stays there.
 *
 * Not yet implemented: TSP generation playback (population evolving via
 * parent_walk_ids lineage). This first version only animates the SA
 * selection trajectory and the final result — see WORKLOG.md.
 */

import type { PlaylistDNAViewModel } from "./projector";
import { applySelection, createBlobs, stepPhysics, type BlobSeed, type Blobs } from "./playback";

export type Phase = "candidates" | "sa" | "final";

export interface PlaybackStatus {
  phase: Phase;
  saIteration: number;
  saTotal: number;
}

export interface RendererOptions {
  /** How long the candidate intro phase lasts before SA playback (or final, if no SA trace) starts. */
  candidateIntroMs?: number;
  /** Milliseconds of simulated time per SA iteration advanced. Lower = faster playback. */
  msPerIteration?: number;
  onStatusChange?: (status: PlaybackStatus) => void;
}

const DEFAULT_CANDIDATE_INTRO_MS = 2000;
const DEFAULT_MS_PER_ITERATION = 15;

export class Renderer {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly width: number;
  private readonly height: number;
  private readonly viewModel: PlaylistDNAViewModel;
  private readonly candidateIntroMs: number;
  private readonly msPerIteration: number;
  private readonly onStatusChange: RendererOptions["onStatusChange"];

  private blobs: Blobs;
  private phase: Phase = "candidates";
  private phaseElapsedMs = 0;
  private saIterationIndex = -1;
  private saAccumulatorMs = 0;

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
    this.onStatusChange = options.onStatusChange;

    const entries: BlobSeed[] = [
      { id: viewModel.seed.trackId, genres: viewModel.seed.genres },
      ...[...viewModel.candidates.values()].map((c) => ({ id: c.trackId, genres: c.genres })),
    ];
    this.blobs = createBlobs(entries, this.width, this.height);
    this.draw();
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
    this.blobs = stepPhysics(this.blobs, dtMs, this.width, this.height);

    switch (this.phase) {
      case "candidates":
        this.phaseElapsedMs += dtMs;
        if (this.phaseElapsedMs >= this.candidateIntroMs) {
          this.enterSAPhaseOrSkipToFinal();
        }
        break;
      case "sa":
        this.advanceSA(dtMs);
        break;
      case "final":
        break; // final selection already applied, nothing more to advance
    }
  }

  private lastSAEpisode() {
    const episodes = this.viewModel.saEpisodes;
    return episodes.length > 0 ? episodes[episodes.length - 1] : undefined;
  }

  private enterSAPhaseOrSkipToFinal(): void {
    const episode = this.lastSAEpisode();
    if (!episode || !episode.selectionsAfter || !episode.initialSelection) {
      this.enterFinalPhase();
      return;
    }
    this.phase = "sa";
    this.saIterationIndex = -1;
    this.saAccumulatorMs = 0;
    this.blobs = applySelection(this.blobs, episode.initialSelection);
  }

  private advanceSA(dtMs: number): void {
    const episode = this.lastSAEpisode();
    if (!episode || !episode.selectionsAfter) {
      this.enterFinalPhase();
      return;
    }

    this.saAccumulatorMs += dtMs;
    while (this.saAccumulatorMs >= this.msPerIteration && this.saIterationIndex < episode.iterations.length - 1) {
      this.saAccumulatorMs -= this.msPerIteration;
      this.saIterationIndex++;
      this.blobs = applySelection(this.blobs, episode.selectionsAfter[this.saIterationIndex]!);
    }

    if (this.saIterationIndex >= episode.iterations.length - 1) {
      this.enterFinalPhase();
    }
  }

  private enterFinalPhase(): void {
    this.phase = "final";
    this.blobs = applySelection(this.blobs, new Set(this.viewModel.final.trackIds));
  }

  private draw(): void {
    this.ctx.clearRect(0, 0, this.width, this.height);
    const seedId = this.viewModel.seed.trackId;

    for (const blob of this.blobs.values()) {
      this.ctx.beginPath();
      this.ctx.arc(blob.x, blob.y, blob.radius, 0, Math.PI * 2);
      this.ctx.fillStyle = blob.color;
      this.ctx.fill();

      if (blob.id === seedId) {
        this.ctx.lineWidth = 3;
        this.ctx.strokeStyle = "white";
        this.ctx.stroke();
      }
    }
  }

  private reportStatus(): void {
    if (!this.onStatusChange) return;
    const episode = this.lastSAEpisode();
    this.onStatusChange({
      phase: this.phase,
      saIteration: this.saIterationIndex + 1,
      saTotal: episode?.iterations.length ?? 0,
    });
  }
}
