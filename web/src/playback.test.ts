import assert from "node:assert/strict";
import { test } from "node:test";

import { genreColor } from "./colors";
import { BASE_RADIUS, SELECTED_RADIUS, applyAttraction, applySelection, createBlobs, stepPhysics } from "./playback";

/** Deterministic replacement for Math.random: cycles through a fixed sequence. */
function fixedSequence(values: number[]): () => number {
  let i = 0;
  return () => {
    const v = values[i % values.length]!;
    i++;
    return v;
  };
}

test("createBlobs places every entry within canvas bounds", () => {
  const blobs = createBlobs(
    [
      { id: "a", genres: ["rock"] },
      { id: "b", genres: [] },
    ],
    800,
    600,
    fixedSequence([0, 0.5, 1, 0.25, 0.75, 0.9]),
  );

  assert.equal(blobs.size, 2);
  for (const blob of blobs.values()) {
    assert.ok(blob.x - blob.radius >= 0 && blob.x + blob.radius <= 800);
    assert.ok(blob.y - blob.radius >= 0 && blob.y + blob.radius <= 600);
    assert.equal(blob.radius, BASE_RADIUS);
    assert.equal(blob.selected, false);
  }
});

test("createBlobs colors each blob by its genres, matching genreColor directly", () => {
  const blobs = createBlobs([{ id: "a", genres: ["gospel"] }], 800, 600, fixedSequence([0.5]));
  assert.equal(blobs.get("a")!.color, genreColor(["gospel"]));
});

test("stepPhysics with zero jitter (random always returns 0.5) moves a blob by exactly velocity * dt", () => {
  const noJitter = fixedSequence([0.5]); // (0.5 - 0.5) * anything = 0, velocity never perturbed
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, noJitter);
  const before = blobs.get("a")!;

  blobs = stepPhysics(blobs, 100, 800, 600, noJitter);

  const after = blobs.get("a")!;
  assert.ok(Math.abs(after.x - (before.x + before.vx * 100)) < 1e-9);
  assert.ok(Math.abs(after.y - (before.y + before.vy * 100)) < 1e-9);
  assert.equal(after.vx, before.vx);
  assert.equal(after.vy, before.vy);
});

test("stepPhysics bounces off the left/top edge instead of leaving the canvas", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  // Force the blob to the very edge, moving further out of bounds.
  const forced = new Map(blobs);
  forced.set("a", { ...forced.get("a")!, x: BASE_RADIUS, y: BASE_RADIUS, vx: -1, vy: -1 });

  const next = stepPhysics(forced, 1000, 800, 600, fixedSequence([0.5]));

  const blob = next.get("a")!;
  assert.equal(blob.x, BASE_RADIUS);
  assert.equal(blob.y, BASE_RADIUS);
  assert.ok(blob.vx > 0, "velocity should have flipped to positive after bouncing off the left edge");
  assert.ok(blob.vy > 0, "velocity should have flipped to positive after bouncing off the top edge");
});

test("stepPhysics bounces off the right/bottom edge", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  const forced = new Map(blobs);
  forced.set("a", { ...forced.get("a")!, x: 800 - BASE_RADIUS, y: 600 - BASE_RADIUS, vx: 1, vy: 1 });

  const next = stepPhysics(forced, 1000, 800, 600, fixedSequence([0.5]));

  const blob = next.get("a")!;
  assert.equal(blob.x, 800 - BASE_RADIUS);
  assert.equal(blob.y, 600 - BASE_RADIUS);
  assert.ok(blob.vx < 0);
  assert.ok(blob.vy < 0);
});

test("stepPhysics never mutates the map passed in", () => {
  const blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  const beforeX = blobs.get("a")!.x;

  stepPhysics(blobs, 500, 800, 600, fixedSequence([0.9]));

  assert.equal(blobs.get("a")!.x, beforeX, "the original map must be untouched");
});

test("applySelection grows selected blobs and shrinks deselected ones", () => {
  let blobs = createBlobs(
    [
      { id: "a", genres: [] },
      { id: "b", genres: [] },
    ],
    800,
    600,
    fixedSequence([0.5]),
  );

  blobs = applySelection(blobs, new Set(["a"]));
  assert.equal(blobs.get("a")!.selected, true);
  assert.equal(blobs.get("a")!.radius, SELECTED_RADIUS);
  assert.equal(blobs.get("b")!.selected, false);
  assert.equal(blobs.get("b")!.radius, BASE_RADIUS);

  // Toggling to a different selection must un-select "a" again, not just add "b".
  blobs = applySelection(blobs, new Set(["b"]));
  assert.equal(blobs.get("a")!.selected, false);
  assert.equal(blobs.get("a")!.radius, BASE_RADIUS);
  assert.equal(blobs.get("b")!.selected, true);
  assert.equal(blobs.get("b")!.radius, SELECTED_RADIUS);
});

// ---------------------------------------------------------------------------
// jitterScale — the "settling as temperature cools" behavior
// ---------------------------------------------------------------------------

test("stepPhysics with jitterScale=0 injects no new randomness (velocity carries over unperturbed)", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  const forced = new Map(blobs);
  forced.set("a", { ...forced.get("a")!, vx: 0.01, vy: -0.005 });

  // random() returns 0.9 here -- if jitterScale actually multiplied it to 0,
  // the perturbation term must vanish regardless of what random() returns.
  const next = stepPhysics(forced, 100, 800, 600, fixedSequence([0.9]), 0);

  const blob = next.get("a")!;
  assert.equal(blob.vx, 0.01);
  assert.equal(blob.vy, -0.005);
});

test("stepPhysics with jitterScale=1 (default) does perturb velocity when random() != 0.5", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  const forced = new Map(blobs);
  forced.set("a", { ...forced.get("a")!, vx: 0.01, vy: -0.005 });

  const next = stepPhysics(forced, 100, 800, 600, fixedSequence([0.9]), 1);

  const blob = next.get("a")!;
  assert.notEqual(blob.vx, 0.01, "velocity should have been perturbed away from its starting value");
});

// ---------------------------------------------------------------------------
// applyAttraction — the actual "convergence" signal
// ---------------------------------------------------------------------------

test("applyAttraction leaves unselected blobs completely untouched", () => {
  const blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  const before = blobs.get("a")!;

  const next = applyAttraction(blobs, { x: 0, y: 0 }, 1, 1000);

  assert.deepEqual(next.get("a"), before);
});

test("applyAttraction pulls a selected blob toward the target, closing the gap over time", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  blobs = applySelection(blobs, new Set(["a"]));
  const start = blobs.get("a")!;
  const target = { x: 0, y: 0 };
  const startDistance = Math.hypot(start.x - target.x, start.y - target.y);

  let current = blobs;
  for (let i = 0; i < 20; i++) {
    current = applyAttraction(current, target, 2, 100);
  }

  const after = current.get("a")!;
  const endDistance = Math.hypot(after.x - target.x, after.y - target.y);
  assert.ok(endDistance < startDistance, "repeated attraction steps must close the distance to the target");
});

test("applyAttraction with strength=0 is a no-op even for selected blobs", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  blobs = applySelection(blobs, new Set(["a"]));
  const before = blobs.get("a")!;

  const next = applyAttraction(blobs, { x: 0, y: 0 }, 0, 1000);

  assert.equal(next.get("a")!.x, before.x);
  assert.equal(next.get("a")!.y, before.y);
});

test("applyAttraction never mutates the map passed in", () => {
  let blobs = createBlobs([{ id: "a", genres: [] }], 800, 600, fixedSequence([0.5]));
  blobs = applySelection(blobs, new Set(["a"]));
  const beforeX = blobs.get("a")!.x;

  applyAttraction(blobs, { x: 0, y: 0 }, 5, 1000);

  assert.equal(blobs.get("a")!.x, beforeX);
});
