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
  /**
   * Deliberately a separate flag from `selected`, not reused for it. During
   * TSP playback every remaining blob is already `selected` (TSP only
   * reorders the fixed final set, doesn't change membership) — `selected`
   * driving both radius and attraction toward the seed, at the same time as
   * needing to spotlight one specific blob as the "currently being visited
   * in this walk order" pointer, would mean two unrelated concerns (which
   * tracks are chosen vs. where the chase animation currently is) fighting
   * over one field. That's exactly the kind of scoping mistake Phase 22
   * caught elsewhere (a physics parameter bleeding onto blobs it wasn't
   * meant to affect) — keeping them separate avoids repeating it here.
   */
  highlighted: boolean;
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
      highlighted: false,
    });
  }
  return blobs;
}

/**
 * Advances every blob by dtMs: gentle random-walk jitter on velocity
 * (damped so it can't run away), move, bounce off the canvas edges.
 * Returns a new Blobs map — never mutates the one passed in.
 *
 * selectedJitterScale (0..1, default 1) scales only the *new* random
 * perturbation added this step, and only for blobs that are currently
 * `selected` — unselected blobs always get the full, constant ambient
 * jitter (scale 1), regardless of this parameter. That scoping matters:
 * the renderer passes the current SA iteration's temperature here
 * (SimulatedAnnealingConfig cools from 1.0 toward 0.01) so the *selected*
 * cluster visibly settles as the anneal converges. Applying that same
 * cooling to every blob was a real bug caught by actually watching the
 * animation — temperature spends most of a 1000-iteration run at low
 * values, so the entire candidate pool (including candidates that were
 * never selected and have nothing to do with the anneal's temperature)
 * would nearly freeze for most of playback, reading as "nothing is
 * happening" rather than "the chosen tracks are settling."
 */
export function stepPhysics(
  blobs: Blobs,
  dtMs: number,
  width: number,
  height: number,
  random: RandomFn = Math.random,
  selectedJitterScale = 1,
): Blobs {
  const next: Blobs = new Map();
  for (const blob of blobs.values()) {
    const jitterScale = blob.selected ? selectedJitterScale : 1;
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

/**
 * Marks exactly one blob (or none, if highlightedId is null) as
 * `highlighted` — the TSP "chase" pointer tracing through the current
 * generation's best walk order. Purely a draw-time visual flag (see
 * renderer.ts's draw()); doesn't affect radius or attraction, unlike
 * `selected` — see BlobState.highlighted's doc comment for why they're
 * kept separate.
 */
export function applyHighlight(blobs: Blobs, highlightedId: string | null): Blobs {
  const next: Blobs = new Map();
  for (const blob of blobs.values()) {
    next.set(blob.id, { ...blob, highlighted: blob.id === highlightedId });
  }
  return next;
}

/**
 * Keeps only the blobs whose id is in `keepIds`, dropping everything
 * else. Used entering the TSP phase: TSP only ever reorders the fixed
 * final selected set, so candidates that were never selected have
 * nothing to do with it and shouldn't keep sitting on screen unexplained
 * (or worse, keep being affected by TSP-phase physics parameters that
 * were never meant to apply to them — the same class of bug as Phase 22).
 */
export function pruneTo(blobs: Blobs, keepIds: ReadonlySet<string>): Blobs {
  const next: Blobs = new Map();
  for (const blob of blobs.values()) {
    if (keepIds.has(blob.id)) next.set(blob.id, blob);
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
