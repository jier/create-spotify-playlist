import assert from "node:assert/strict";
import { test } from "node:test";

import { distance, jaccardDistance, type DistanceWeights } from "./distance";

// These mirror tests/test_distance.py's cases exactly (same inputs, same
// expected values) to prove numeric parity with the backend formula, not
// just "looks similar."

test("jaccardDistance: identical genres -> 0", () => {
  assert.equal(jaccardDistance(new Set(["rock"]), new Set(["rock"])), 0.0);
});

test("jaccardDistance: disjoint genres -> 1", () => {
  assert.equal(jaccardDistance(new Set(["rock"]), new Set(["pop"])), 1.0);
});

test("jaccardDistance: partial overlap", () => {
  assert.equal(jaccardDistance(new Set(["rock", "pop"]), new Set(["pop", "jazz"])), 1.0 - 1 / 3);
});

test("jaccardDistance: both empty -> 1 (matches jaccard_distance's union-empty guard)", () => {
  assert.equal(jaccardDistance(new Set(), new Set()), 1.0);
});

test("distance combines genre and year distance with weights", () => {
  const weights: DistanceWeights = { genreWeight: 1.0, yearWeight: 0.5 };
  const a = { genres: ["rock"], releaseYear: 2000 };
  const b = { genres: ["pop"], releaseYear: 2010 };

  assert.equal(distance(a, b, weights), 1.0 * 1.0 + 0.5 * 0.2);
});

test("distance caps year distance at 1", () => {
  const weights: DistanceWeights = { genreWeight: 0.0, yearWeight: 1.0 };
  const a = { genres: ["rock"], releaseYear: 1970 };
  const b = { genres: ["rock"], releaseYear: 2020 };

  assert.equal(distance(a, b, weights), 1.0);
});

test("distance uses DEFAULT_WEIGHTS matching settings.py's defaults when not specified", () => {
  const a = { genres: ["rock"], releaseYear: 2000 };
  const b = { genres: ["pop"], releaseYear: 2010 };

  // genre_weight=1.0, year_weight=0.5 -- same values as the explicit-weights test above.
  assert.equal(distance(a, b), 1.0 * 1.0 + 0.5 * 0.2);
});
