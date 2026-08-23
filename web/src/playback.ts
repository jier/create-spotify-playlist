/**
 * Pure blob simulation: positions, drift, and selection state. No DOM, no
 * Canvas, no requestAnimationFrame — renderer.ts owns the animation loop
 * and calls these each tick, then draws whatever they return. Same
 * reducer/renderer split as projector.ts, one layer further in.
 *
 * Randomness (initial placement, drift jitter) takes an injectable
 * `random` function defaulting to Math.random, so tests can supply a
 * deterministic sequence instead of asserting on non-deterministic output.
 */

import { genreColor } from "./colors";

export type RandomFn = () => number;

export interface BlobState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  selected: boolean;
}

export type Blobs = Map<string, BlobState>;

export const BASE_RADIUS = 18;
export const SELECTED_RADIUS = 28;
/** px/ms baseline drift speed — deliberately slow, this is a lava lamp, not a bounce simulation. */
export const DRIFT_SPEED = 0.02;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export interface BlobSeed {
  id: string;
  genres: readonly string[];
}

/** Initial blob state for every entry: random position within bounds, colored by genre, unselected. */
export function createBlobs(entries: readonly BlobSeed[], width: number, height: number, random: RandomFn = Math.random): Blobs {
  const blobs: Blobs = new Map();
  for (const entry of entries) {
    const radius = BASE_RADIUS;
    blobs.set(entry.id, {
      id: entry.id,
      x: radius + random() * Math.max(0, width - 2 * radius),
      y: radius + random() * Math.max(0, height - 2 * radius),
      vx: (random() - 0.5) * DRIFT_SPEED,
      vy: (random() - 0.5) * DRIFT_SPEED,
      radius,
      color: genreColor(entry.genres),
      selected: false,
    });
  }
  return blobs;
}

/**
 * Advances every blob by dtMs: gentle random-walk jitter on velocity
 * (damped so it can't run away), move, bounce off the canvas edges.
 * Returns a new Blobs map — never mutates the one passed in.
 *
 * jitterScale (0..1, default 1) scales only the *new* random perturbation
 * added this step, not the blob's existing velocity/movement. The renderer
 * passes the current SA iteration's temperature here (SimulatedAnnealingConfig
 * cools from 1.0 toward 0.01) so blobs visibly settle — less new chaotic
 * energy injected — as the anneal cools, instead of jittering at a constant
 * rate for the whole run regardless of how close it is to converging.
 */
export function stepPhysics(
  blobs: Blobs,
  dtMs: number,
  width: number,
  height: number,
  random: RandomFn = Math.random,
  jitterScale = 1,
): Blobs {
  const next: Blobs = new Map();
  for (const blob of blobs.values()) {
    let vx = clamp(blob.vx + (random() - 0.5) * DRIFT_SPEED * 0.1 * jitterScale, -DRIFT_SPEED * 2, DRIFT_SPEED * 2);
    let vy = clamp(blob.vy + (random() - 0.5) * DRIFT_SPEED * 0.1 * jitterScale, -DRIFT_SPEED * 2, DRIFT_SPEED * 2);

    let x = blob.x + vx * dtMs;
    let y = blob.y + vy * dtMs;

    if (x - blob.radius < 0) {
      x = blob.radius;
      vx = Math.abs(vx);
    } else if (x + blob.radius > width) {
      x = width - blob.radius;
      vx = -Math.abs(vx);
    }
    if (y - blob.radius < 0) {
      y = blob.radius;
      vy = Math.abs(vy);
    } else if (y + blob.radius > height) {
      y = height - blob.radius;
      vy = -Math.abs(vy);
    }

    next.set(blob.id, { ...blob, x, y, vx, vy });
  }
  return next;
}

/**
 * Marks which blobs are currently "selected" (part of the SA/final
 * selection at this point in playback) and grows/shrinks them
 * accordingly. Returns a new Blobs map.
 */
export function applySelection(blobs: Blobs, selectedIds: ReadonlySet<string>): Blobs {
  const next: Blobs = new Map();
  for (const blob of blobs.values()) {
    const selected = selectedIds.has(blob.id);
    next.set(blob.id, { ...blob, selected, radius: selected ? SELECTED_RADIUS : BASE_RADIUS });
  }
  return next;
}

export interface AttractionTarget {
  x: number;
  y: number;
}

/**
 * Pulls every *selected* blob a fraction of the way toward `target` each
 * step; unselected blobs are left untouched. This is the actual
 * "convergence" signal — without it, `selected` only changed radius
 * (see applySelection), so the visualization never showed anything
 * gathering together as the anneal progressed, just uniform random drift
 * regardless of selection state.
 *
 * strength is a rate, not a distance — roughly "fraction of the remaining
 * gap closed per second". 0 = no pull (selection would only show via
 * radius, the old behavior). Higher = snaps toward the target faster.
 */
export function applyAttraction(blobs: Blobs, target: AttractionTarget, strength: number, dtMs: number): Blobs {
  const next: Blobs = new Map();
  const pull = clamp(strength * (dtMs / 1000), 0, 1);
  for (const blob of blobs.values()) {
    if (!blob.selected || pull === 0) {
      next.set(blob.id, blob);
      continue;
    }
    next.set(blob.id, {
      ...blob,
      x: blob.x + (target.x - blob.x) * pull,
      y: blob.y + (target.y - blob.y) * pull,
    });
  }
  return next;
}
