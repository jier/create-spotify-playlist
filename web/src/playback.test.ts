import assert from "node:assert/strict";
import { test } from "node:test";

import { genreColor } from "./colors";
import { BASE_RADIUS, SELECTED_RADIUS, applySelection, createBlobs, stepPhysics } from "./playback";

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
